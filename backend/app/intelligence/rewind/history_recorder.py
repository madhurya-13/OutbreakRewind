"""Central append-only investigation history and entity version recording."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import HistoricalEntityVersion, InvestigationHistoryEvent
from .utils import (KNOWN_INVESTIGATIONS, aware, dumps, loads, new_id, utcnow)

INVESTIGATOR_EVENTS = {
    "EVIDENCE_RECORD_VERIFIED", "EVIDENCE_RECORD_CORRECTED", "EVIDENCE_RECORD_DISPUTED",
    "EVENT_UPDATED", "EVENT_DATE_REVISED", "EVENT_VERIFIED", "EVENT_DISPUTED",
    "RELATIONSHIP_REVIEWED", "RELATIONSHIP_DISPUTED",
    "CONTRADICTION_REVIEWED", "CONTRADICTION_CONFIRMED", "CONTRADICTION_RESOLVED",
    "CONTRADICTION_DISMISSED", "CONTRADICTION_REOPENED",
    "HYPOTHESIS_CREATED", "HYPOTHESIS_UPDATED", "HYPOTHESIS_STATUS_CHANGED",
    "HYPOTHESIS_ARCHIVED", "HYPOTHESIS_EVIDENCE_LINKED", "HYPOTHESIS_EVIDENCE_RECLASSIFIED",
    "HYPOTHESIS_EVIDENCE_WITHDRAWN", "INVESTIGATOR_NOTE_ADDED", "SNAPSHOT_CREATED",
}


def known_investigations() -> dict[str, str]:
    return dict(KNOWN_INVESTIGATIONS)


def event_module(event_type: str) -> str:
    if event_type.startswith("EVIDENCE"):
        return "EVIDENCE"
    if event_type.startswith(("TIMELINE", "EVENT_")):
        return "TIMELINE"
    if event_type.startswith(("NETWORK", "RELATIONSHIP")):
        return "NETWORK"
    if event_type.startswith("CONTRADICTION"):
        return "CONTRADICTIONS"
    if event_type.startswith("HYPOTHESIS"):
        return "HYPOTHESES"
    if event_type.startswith("INVESTIGATION"):
        return "INVESTIGATION"
    if event_type.startswith("SNAPSHOT"):
        return "SNAPSHOTS"
    if event_type.startswith("INVESTIGATOR"):
        return "INVESTIGATOR"
    return "SYSTEM"


def record_history_event(
    db: Session,
    investigation_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    description: str,
    *,
    previous_state: Any = None,
    new_state: Any = None,
    actor_type: str | None = None,
    actor_id: str = "system",
    source_reference: Any = None,
    related_event_id: str | None = None,
    change_reason: str = "",
    metadata: Any = None,
    entity_version: int = 1,
    recorded_at: datetime | None = None,
    dedupe: bool = False,
) -> InvestigationHistoryEvent:
    """Record one meaningful change without committing the caller's transaction.

    ``dedupe`` is used for repeatable reconstruction operations. A repeated
    operation with an identical resulting state returns the prior event rather
    than creating a duplicate.
    """
    timestamp = aware(recorded_at) or utcnow()
    previous_json, new_json = dumps(previous_state or {}), dumps(new_state or {})
    if dedupe:
        latest = db.scalar(select(InvestigationHistoryEvent).where(
            InvestigationHistoryEvent.investigation_id == investigation_id,
            InvestigationHistoryEvent.event_type == event_type,
            InvestigationHistoryEvent.entity_type == entity_type,
            InvestigationHistoryEvent.entity_id == entity_id,
        ).order_by(InvestigationHistoryEvent.recorded_at.desc()).limit(1))
        if latest and latest.new_state == new_json:
            return latest
    event = InvestigationHistoryEvent(
        event_id=new_id("EVH"),
        investigation_id=investigation_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_version=max(int(entity_version or 1), 1),
        description=(description or "")[:5000],
        previous_state=previous_json,
        new_state=new_json,
        actor_type=(actor_type or ("INVESTIGATOR" if event_type in INVESTIGATOR_EVENTS else "SYSTEM")).upper(),
        actor_id=(actor_id or "system")[:120],
        source_reference=dumps(source_reference or {}),
        related_event_id=related_event_id,
        change_reason=(change_reason or "")[:5000],
        metadata_json=dumps(metadata or {}),
        recorded_at=timestamp,
    )
    db.add(event)
    return event


def record_entity_version(
    db: Session,
    investigation_id: str,
    entity_type: str,
    entity_id: str,
    state: Any,
    *,
    recorded_by: str = "system",
    change_reason: str = "",
    source_reference: Any = None,
    valid_from: datetime | None = None,
    recorded_at: datetime | None = None,
) -> HistoricalEntityVersion:
    """Append an immutable version, closing the previous version's valid interval."""
    timestamp = aware(recorded_at) or utcnow()
    payload = dumps(state)
    latest = db.scalar(select(HistoricalEntityVersion).where(
        HistoricalEntityVersion.entity_type == entity_type,
        HistoricalEntityVersion.entity_id == entity_id,
    ).order_by(HistoricalEntityVersion.version_number.desc()).limit(1))
    if latest and latest.state_data == payload:
        return latest
    if latest and latest.valid_to is None:
        latest.valid_to = timestamp
    version = (latest.version_number + 1) if latest else 1
    item = HistoricalEntityVersion(
        version_id=new_id("HEV"),
        investigation_id=investigation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        version_number=version,
        state_data=payload,
        valid_from=aware(valid_from) or timestamp,
        valid_to=None,
        recorded_at=timestamp,
        recorded_by=(recorded_by or "system")[:120],
        change_reason=(change_reason or "")[:5000],
        source_reference=dumps(source_reference or {}),
    )
    db.add(item)
    return item


def event_dict(item: InvestigationHistoryEvent, include_states: bool = True) -> dict[str, Any]:
    result = {
        "event_id": item.event_id,
        "investigation_id": item.investigation_id,
        "event_type": item.event_type,
        "module": event_module(item.event_type),
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "entity_version": item.entity_version,
        "description": item.description,
        "actor_type": item.actor_type,
        "actor_id": item.actor_id,
        "source_reference": loads(item.source_reference, {}),
        "related_event_id": item.related_event_id,
        "change_reason": item.change_reason,
        "metadata": loads(item.metadata_json, {}),
        "recorded_at": item.recorded_at.isoformat(),
    }
    if include_states:
        result["previous_state"] = loads(item.previous_state, {})
        result["new_state"] = loads(item.new_state, {})
    return result


def trigger_automatic_snapshot(
    db: Session,
    investigation_id: str,
    snapshot_type: str,
    *,
    created_by: str = "system",
    description: str = "",
) -> Any:
    """Create an automatic snapshot through the snapshot manager (lazy import)."""
    from .snapshot_manager import create_snapshot
    return create_snapshot(
        db, investigation_id, snapshot_type=snapshot_type,
        created_by=created_by, name=f"{snapshot_type.replace('_', ' ').title()}",
        description=description, event_cutoff=utcnow(),
    )