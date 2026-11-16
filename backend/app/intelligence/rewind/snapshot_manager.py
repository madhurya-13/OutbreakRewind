"""Immutable investigation snapshots with content-hash integrity validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import InvestigationHistoryEvent, InvestigationSnapshot
from .historical_reconstructor import reconstruct_investigation_as_of
from .history_recorder import record_history_event
from .utils import (content_hash, dumps, iso, loads, new_id, parse_timestamp,
                    utcnow)

SCHEMA_VERSION = "7.0"
SNAPSHOT_TYPES = {
    "MANUAL_SNAPSHOT", "AUTOMATIC_SNAPSHOT", "MILESTONE_SNAPSHOT",
    "PRE_RECONSTRUCTION_SNAPSHOT", "POST_RECONSTRUCTION_SNAPSHOT",
    "PRE_ASSESSMENT_SNAPSHOT", "POST_ASSESSMENT_SNAPSHOT",
}


def create_snapshot(
    db: Session,
    investigation_id: str,
    *,
    snapshot_type: str = "MANUAL_SNAPSHOT",
    created_by: str = "investigator",
    name: str = "",
    description: str = "",
    event_cutoff: str | datetime | None = None,
) -> InvestigationSnapshot:
    cutoff = parse_timestamp(event_cutoff, field="event_cutoff") if event_cutoff else utcnow()
    if snapshot_type not in SNAPSHOT_TYPES:
        raise ValueError("Unsupported snapshot type")
    state = reconstruct_investigation_as_of(investigation_id, cutoff, db)
    data = {
        "schema_version": SCHEMA_VERSION,
        "investigation_id": investigation_id,
        "investigation": state["investigation"],
        "as_of": state["as_of"],
        "coverage": state["coverage"],
        "summary": state["summary"],
        "evidence": state["evidence"],
        "records": state["records"],
        "timeline": state["timeline"],
        "network": state["network"],
        "contradictions": state["contradictions"],
        "hypotheses": state["hypotheses"],
        "recent_changes": state["recent_changes"],
        "history": state.get("history", state["recent_changes"]),
        "provenance": state["provenance"],
    }
    sequence = db.scalar(select(func.count()).select_from(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id,
        InvestigationHistoryEvent.recorded_at <= cutoff,
    )) or 0
    timestamp = utcnow()
    item = InvestigationSnapshot(
        snapshot_id=new_id("ISNAP"),
        investigation_id=investigation_id,
        snapshot_name=(name or f"{snapshot_type.replace('_', ' ').title()} · {cutoff.date().isoformat()}")[:255],
        description=description or "Immutable point-in-time investigation snapshot.",
        snapshot_type=snapshot_type,
        snapshot_data=dumps(data),
        event_cutoff=cutoff,
        event_sequence=int(sequence),
        included_entity_counts=dumps(state["summary"]),
        snapshot_schema_version=SCHEMA_VERSION,
        integrity_hash=content_hash(data),
        integrity_status="VALID",
        created_by=(created_by or "investigator")[:120],
        created_at=timestamp,
    )
    db.add(item)
    db.flush()
    record_history_event(
        db, investigation_id, "SNAPSHOT_CREATED", "SNAPSHOT", item.snapshot_id,
        f"Created {snapshot_type.replace('_', ' ').lower()} '{item.snapshot_name}'.",
        previous_state={}, new_state={"snapshot_id": item.snapshot_id, "snapshot_type": snapshot_type, "event_cutoff": iso(cutoff), "integrity_hash": item.integrity_hash},
        actor_type="INVESTIGATOR" if created_by != "system" else "SYSTEM", actor_id=created_by,
        source_reference={"snapshot_id": item.snapshot_id}, change_reason=description,
        recorded_at=timestamp,
    )
    return item


def snapshot_dict(item: InvestigationSnapshot, include_data: bool = False) -> dict[str, Any]:
    result = {
        "snapshot_id": item.snapshot_id, "investigation_id": item.investigation_id,
        "snapshot_name": item.snapshot_name, "description": item.description,
        "snapshot_type": item.snapshot_type, "event_cutoff": iso(item.event_cutoff),
        "event_sequence": item.event_sequence,
        "included_entity_counts": loads(item.included_entity_counts, {}),
        "snapshot_schema_version": item.snapshot_schema_version,
        "integrity_hash": item.integrity_hash, "integrity_status": item.integrity_status,
        "created_by": item.created_by, "created_at": iso(item.created_at),
    }
    if include_data:
        result["snapshot_data"] = loads(item.snapshot_data, {})
    return result


def validate_snapshot(item: InvestigationSnapshot) -> dict[str, Any]:
    data = loads(item.snapshot_data, None)
    checks: list[dict[str, Any]] = []
    checks.append({"check": "data_deserializes", "passed": isinstance(data, dict)})
    required = {"investigation", "as_of", "coverage", "summary", "evidence", "records", "timeline", "network", "contradictions", "hypotheses", "recent_changes", "provenance"}
    present = set(data.keys()) if isinstance(data, dict) else set()
    checks.append({"check": "required_sections", "passed": required.issubset(present), "missing": sorted(required - present)})
    recomputed = content_hash(data) if isinstance(data, dict) else ""
    checks.append({"check": "content_hash", "passed": recomputed == item.integrity_hash, "expected": item.integrity_hash, "actual": recomputed})
    checks.append({"check": "schema_version", "passed": item.snapshot_schema_version == SCHEMA_VERSION, "actual": item.snapshot_schema_version})
    counts_ok = False
    if isinstance(data, dict):
        summary = data.get("summary") or {}
        counts_ok = (
            len(data.get("evidence") or []) == summary.get("evidence_count")
            and len(data.get("timeline", {}).get("events") or []) == summary.get("event_count")
            and len(data.get("hypotheses") or []) == summary.get("hypothesis_count")
        )
    checks.append({"check": "entity_counts", "passed": counts_ok})
    references_ok = True
    if isinstance(data, dict):
        evidence_ids = {item.get("evidence_id") for item in data.get("evidence") or []}
        for record in data.get("records") or []:
            if record.get("evidence_id") not in evidence_ids:
                references_ok = False
                break
        for event in data.get("timeline", {}).get("events") or []:
            for source in event.get("sources") or []:
                if source.get("evidence_id") and source["evidence_id"] not in evidence_ids and source.get("source_available") is not False:
                    references_ok = False
                    break
    checks.append({"check": "source_references", "passed": references_ok})
    valid = all(check["passed"] for check in checks)
    return {
        "snapshot_id": item.snapshot_id, "valid": valid,
        "integrity_status": "VALID" if valid else "FAILED",
        "stored_integrity_status": item.integrity_status,
        "schema_version": item.snapshot_schema_version,
        "checks": checks, "validated_at": iso(utcnow()),
    }