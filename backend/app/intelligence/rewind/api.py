"""FastAPI routes for Investigation Rewind."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import (InvestigationComparison, InvestigationExport,
                       InvestigationHistoryEvent, InvestigationSnapshot)
from .history_recorder import (event_dict, event_module, known_investigations,
                               record_history_event)
from .hypothesis_evolution import hypothesis_changes, hypothesis_evolution
from .investigation_comparator import compare_investigation_states
from .report_generator import export_path, generate_investigation_export
from .snapshot_manager import (create_snapshot, snapshot_dict,
                               validate_snapshot)
from .historical_reconstructor import coverage_for_investigation, reconstruct_investigation_as_of
from .utils import aware, iso, loads, parse_timestamp, utcnow

router = APIRouter(prefix="/api/rewind", tags=["Investigation Rewind"])


class SnapshotCreate(BaseModel):
    name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=5000)
    snapshot_type: str = "MANUAL_SNAPSHOT"
    created_by: str = "investigator"
    event_cutoff: str | None = None


class ComparisonRequest(BaseModel):
    timestamp_a: str | None = None
    timestamp_b: str | None = None
    snapshot_a_id: str | None = None
    snapshot_b_id: str | None = None
    created_by: str = "investigator"
    save: bool = True


class ExportRequest(BaseModel):
    export_type: Literal["PDF", "CSV", "pdf", "csv"] = "PDF"
    cutoff_timestamp: str | None = None
    snapshot_id: str | None = None
    generated_by: str = "investigator"


def _require_investigation(investigation_id: str) -> None:
    if investigation_id not in known_investigations():
        raise HTTPException(status_code=404, detail="Investigation not found")


def _reconstruct(investigation_id: str, as_of: str, db: Session, compact: bool = False) -> dict:
    _require_investigation(investigation_id)
    try:
        state = reconstruct_investigation_as_of(investigation_id, as_of, db, compact=compact)
        # The UI and history endpoint retrieve the paginated event stream separately. Avoid
        # sending the entire investigation history inside every point-in-time response.
        state.pop("history", None)
        return state
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _compact_state(state: dict) -> dict:
    """Return the UI projection without bulky provenance collections.

    The complete reconstruction remains available from the default endpoint, snapshots, reports,
    and comparisons. This projection keeps every field the Rewind viewer renders while omitting
    the temporal relationship matrix, extracted-record payloads, and nested evidence/review rows.
    """
    state["records"] = []
    state["timeline"]["relationships"] = []
    for event in state["timeline"].get("events") or []:
        event.pop("audit_history", None)
    for relationship in state["network"].get("relationships") or []:
        relationship.pop("sources", None)
    for contradiction in state.get("contradictions") or []:
        contradiction.pop("comparisons", None)
        contradiction.pop("evidence", None)
        contradiction.pop("reviews", None)
    for hypothesis in state.get("hypotheses") or []:
        hypothesis.pop("notes", None)
        hypothesis.pop("review_history", None)
    return state


@router.get("/{investigation_id}/history")
def history(
    investigation_id: str,
    db: Session = Depends(get_db),
    event_type: str | None = None,
    module: str | None = None,
    actor: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
    _require_investigation(investigation_id)
    rows = list(db.scalars(select(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id
    ).order_by(InvestigationHistoryEvent.recorded_at.asc())).all())
    if event_type:
        rows = [item for item in rows if item.event_type == event_type]
    if module:
        rows = [item for item in rows if event_module(item.event_type) == module.upper()]
    if actor:
        rows = [item for item in rows if actor.lower() in item.actor_id.lower()]
    if entity_id:
        rows = [item for item in rows if entity_id in item.entity_id]
    if date_from:
        rows = [item for item in rows if aware(item.recorded_at) >= aware(date_from)]
    if date_to:
        rows = [item for item in rows if aware(item.recorded_at) <= aware(date_to)]
    total = len(rows)
    start = (page - 1) * page_size
    return {"items": [event_dict(item, include_states=False) for item in rows[start:start + page_size]], "total": total, "page": page, "page_size": page_size}


@router.get("/{investigation_id}/history/filters")
def history_filters(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    rows = list(db.scalars(select(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id
    )).all())
    return {
        "event_types": sorted({item.event_type for item in rows}),
        "modules": sorted({event_module(item.event_type) for item in rows}),
        "actors": sorted({item.actor_id for item in rows}),
        "entity_types": sorted({item.entity_type for item in rows}),
    }


@router.get("/{investigation_id}/history/{event_id}")
def history_detail(investigation_id: str, event_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    item = db.get(InvestigationHistoryEvent, event_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="History event not found")
    return event_dict(item)


@router.post("/{investigation_id}/snapshots", status_code=201)
def create_investigation_snapshot(investigation_id: str, payload: SnapshotCreate, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    try:
        item = create_snapshot(
            db, investigation_id, snapshot_type=payload.snapshot_type,
            created_by=payload.created_by, name=payload.name, description=payload.description,
            event_cutoff=payload.event_cutoff,
        )
        db.commit()
        db.refresh(item)
        return snapshot_dict(item, include_data=True)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{investigation_id}/snapshots")
def list_investigation_snapshots(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_investigation(investigation_id)
    rows = list(db.scalars(select(InvestigationSnapshot).where(
        InvestigationSnapshot.investigation_id == investigation_id
    ).order_by(InvestigationSnapshot.created_at.desc())).all())
    return [snapshot_dict(item) for item in rows]


@router.get("/{investigation_id}/snapshots/{snapshot_id}")
def get_investigation_snapshot(investigation_id: str, snapshot_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    item = db.get(InvestigationSnapshot, snapshot_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot_dict(item, include_data=True)


@router.get("/{investigation_id}/snapshots/{snapshot_id}/integrity")
def get_snapshot_integrity(investigation_id: str, snapshot_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    item = db.get(InvestigationSnapshot, snapshot_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return validate_snapshot(item)


@router.get("/{investigation_id}/at")
def at_timestamp(investigation_id: str, as_of: str, compact: bool = False, db: Session = Depends(get_db)) -> dict:
    state = _reconstruct(investigation_id, as_of, db, compact=compact)
    return _compact_state(state) if compact else state


@router.get("/{investigation_id}/at/{timestamp}/summary")
def at_summary(investigation_id: str, timestamp: str, db: Session = Depends(get_db)) -> dict:
    state = _reconstruct(investigation_id, timestamp, db)
    return {"investigation_id": investigation_id, "as_of": state["as_of"], "coverage": state["coverage"], "summary": state["summary"]}


@router.get("/{investigation_id}/at/{timestamp}/timeline")
def at_timeline(investigation_id: str, timestamp: str, db: Session = Depends(get_db)) -> dict:
    state = _reconstruct(investigation_id, timestamp, db)
    return state["timeline"]


@router.get("/{investigation_id}/at/{timestamp}/network")
def at_network(investigation_id: str, timestamp: str, db: Session = Depends(get_db)) -> dict:
    state = _reconstruct(investigation_id, timestamp, db)
    return state["network"]


@router.get("/{investigation_id}/at/{timestamp}/contradictions")
def at_contradictions(investigation_id: str, timestamp: str, db: Session = Depends(get_db)) -> list[dict]:
    state = _reconstruct(investigation_id, timestamp, db)
    return state["contradictions"]


@router.get("/{investigation_id}/at/{timestamp}/hypotheses")
def at_hypotheses(investigation_id: str, timestamp: str, db: Session = Depends(get_db)) -> list[dict]:
    state = _reconstruct(investigation_id, timestamp, db)
    return state["hypotheses"]


@router.post("/{investigation_id}/compare")
def compare(investigation_id: str, payload: ComparisonRequest, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    snapshot_a = db.get(InvestigationSnapshot, payload.snapshot_a_id) if payload.snapshot_a_id else None
    snapshot_b = db.get(InvestigationSnapshot, payload.snapshot_b_id) if payload.snapshot_b_id else None
    if payload.snapshot_a_id and (not snapshot_a or snapshot_a.investigation_id != investigation_id):
        raise HTTPException(status_code=404, detail="First snapshot not found")
    if payload.snapshot_b_id and (not snapshot_b or snapshot_b.investigation_id != investigation_id):
        raise HTTPException(status_code=404, detail="Second snapshot not found")
    if not payload.timestamp_a and not snapshot_a:
        raise HTTPException(status_code=422, detail="timestamp_a or snapshot_a_id is required")
    if not payload.timestamp_b and not snapshot_b:
        raise HTTPException(status_code=422, detail="timestamp_b or snapshot_b_id is required")
    try:
        timestamp_a = parse_timestamp(payload.timestamp_a, field="timestamp_a") if payload.timestamp_a else aware(snapshot_a.event_cutoff)
        timestamp_b = parse_timestamp(payload.timestamp_b, field="timestamp_b") if payload.timestamp_b else aware(snapshot_b.event_cutoff)
        if timestamp_a > timestamp_b:
            raise HTTPException(status_code=422, detail="The first cutoff must be earlier than or equal to the second cutoff")
        state_a = loads(snapshot_a.snapshot_data, {}) if snapshot_a else reconstruct_investigation_as_of(investigation_id, timestamp_a, db)
        state_b = loads(snapshot_b.snapshot_data, {}) if snapshot_b else reconstruct_investigation_as_of(investigation_id, timestamp_b, db)
        result = compare_investigation_states(investigation_id, state_a, state_b)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.save:
        item = InvestigationComparison(
            comparison_id=f"ICMP-{__import__('uuid').uuid4().hex[:16].upper()}", investigation_id=investigation_id,
            snapshot_a_id=payload.snapshot_a_id, snapshot_b_id=payload.snapshot_b_id,
            timestamp_a=timestamp_a, timestamp_b=timestamp_b, comparison_data=__import__('json').dumps(result, default=str),
            comparison_summary=result["summary"], created_by=payload.created_by, created_at=utcnow(),
        )
        db.add(item)
        record_history_event(
            db, investigation_id, "INVESTIGATION_COMPARED", "INVESTIGATION", investigation_id,
            f"Compared historical states {timestamp_a.isoformat()} and {timestamp_b.isoformat()}.",
            previous_state={"as_of": timestamp_a.isoformat()}, new_state={"as_of": timestamp_b.isoformat(), "difference_count": len(result["differences"])},
            actor_type="INVESTIGATOR", actor_id=payload.created_by, source_reference={"comparison_id": item.comparison_id},
        )
        db.commit()
        result["comparison_id"] = item.comparison_id
    return result


@router.get("/{investigation_id}/comparisons")
def comparisons(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_investigation(investigation_id)
    rows = list(db.scalars(select(InvestigationComparison).where(
        InvestigationComparison.investigation_id == investigation_id
    ).order_by(InvestigationComparison.created_at.desc())).all())
    return [{
        "comparison_id": item.comparison_id, "snapshot_a_id": item.snapshot_a_id,
        "snapshot_b_id": item.snapshot_b_id, "timestamp_a": iso(item.timestamp_a),
        "timestamp_b": iso(item.timestamp_b), "comparison_summary": item.comparison_summary,
        "created_by": item.created_by, "created_at": iso(item.created_at),
    } for item in rows]


@router.get("/{investigation_id}/hypotheses/{hypothesis_id}/evolution")
def hypothesis_evolution_route(investigation_id: str, hypothesis_id: str, as_of: str | None = None, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    return hypothesis_evolution(investigation_id, hypothesis_id, db, as_of)


@router.get("/{investigation_id}/hypotheses/{hypothesis_id}/changes")
def hypothesis_changes_route(investigation_id: str, hypothesis_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    return hypothesis_changes(investigation_id, hypothesis_id, db)


@router.post("/{investigation_id}/export", status_code=201)
def export(investigation_id: str, payload: ExportRequest, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    try:
        item = generate_investigation_export(
            db, investigation_id, export_type=payload.export_type.upper(),
            cutoff_timestamp=payload.cutoff_timestamp, snapshot_id=payload.snapshot_id,
            generated_by=payload.generated_by,
        )
        db.commit()
        db.refresh(item)
        return _export_dict(item)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Historical report generation failed") from exc


def _export_dict(item: InvestigationExport) -> dict:
    return {
        "export_id": item.export_id, "investigation_id": item.investigation_id,
        "export_type": item.export_type, "cutoff_timestamp": iso(item.cutoff_timestamp),
        "snapshot_reference": item.snapshot_reference, "generated_by": item.generated_by,
        "generated_at": iso(item.generated_at), "export_status": item.export_status,
        "metadata": loads(item.metadata_json, {}),
        "download_url": f"/api/rewind/{item.investigation_id}/exports/{item.export_id}/download" if item.export_status == "COMPLETED" else None,
    }


@router.get("/{investigation_id}/exports")
def exports(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_investigation(investigation_id)
    rows = list(db.scalars(select(InvestigationExport).where(
        InvestigationExport.investigation_id == investigation_id
    ).order_by(InvestigationExport.generated_at.desc())).all())
    return [_export_dict(item) for item in rows]


@router.get("/{investigation_id}/exports/{export_id}")
def export_metadata(investigation_id: str, export_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    item = db.get(InvestigationExport, export_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Export not found")
    return _export_dict(item)


@router.get("/{investigation_id}/exports/{export_id}/download")
def download_export(investigation_id: str, export_id: str, db: Session = Depends(get_db)):
    _require_investigation(investigation_id)
    item = db.get(InvestigationExport, export_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Export not found")
    path = export_path(item)
    if path is None:
        raise HTTPException(status_code=404, detail="Export file unavailable")
    media = "application/pdf" if item.export_type == "PDF" else "text/csv"
    return FileResponse(path, media_type=media, filename=Path(item.file_reference).name)


@router.get("/{investigation_id}/coverage")
def coverage(investigation_id: str, as_of: str | None = None, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    try:
        return coverage_for_investigation(investigation_id, db, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{investigation_id}/validate")
def validate(investigation_id: str, as_of: str | None = None, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    cutoff = as_of or utcnow().isoformat()
    state = _reconstruct(investigation_id, cutoff, db)
    cutoff_at = parse_timestamp(cutoff, field="as_of")
    checks = [
        {"check": "summary_matches_evidence", "passed": state["summary"]["evidence_count"] == len(state["evidence"])},
        {"check": "summary_matches_timeline", "passed": state["summary"]["event_count"] == len(state["timeline"]["events"])},
        {"check": "no_future_evidence", "passed": all((parse_timestamp(item["uploaded_at"]) <= cutoff_at) for item in state["evidence"])},
        {"check": "no_future_timeline_events", "passed": all((parse_timestamp(item["recorded_at"]) <= cutoff_at) for item in state["timeline"]["events"])},
        {"check": "read_only", "passed": True, "because": "Reconstruction only reads database state."},
    ]
    return {"investigation_id": investigation_id, "as_of": state["as_of"], "valid": all(item["passed"] for item in checks), "checks": checks, "coverage": state["coverage"]}