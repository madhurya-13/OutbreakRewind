"""Resolve, snapshot, and catalogue existing investigation source records.

The hypothesis engine never copies or mutates Milestone 2-5 records. It stores a
point-in-time snapshot of the source reference so that an investigator can still
inspect what was linked even if the source is later corrected or withdrawn.
"""
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import (
    Contradiction,
    EvidenceRecord,
    GraphNode,
    GraphRelationship,
    ReconstructedEvent,
    TemporalFinding,
)
from .evidence_assessor import suggest_strength
from .source_reliability import suggest_reliability


def _loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _record_rows(record: EvidenceRecord) -> list[dict[str, Any]]:
    rows = _loads(record.records_json, [])
    return rows if isinstance(rows, list) else []


def _find_extracted_record(db: Session, investigation_id: str, source_id: str) -> tuple[EvidenceRecord, dict[str, Any]] | None:
    records = db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all()
    for evidence in records:
        for row in _record_rows(evidence):
            if str(row.get("record_id")) == source_id:
                return evidence, row
    return None


def _event(for_record: dict[str, Any]) -> str:
    return str(record_value(for_record, "description") or record_value(for_record, "event_type") or "record").strip()


def record_value(record: dict[str, Any], key: str, default: Any = None) -> Any:
    return record.get(key, default)


def _event_title(row: dict[str, Any]) -> str:
    person = row.get("person_id") or "unknown person"
    description = str(row.get("description") or "extracted record").strip()
    if len(description) > 110:
        description = description[:107] + "..."
    return f"{person} · {description}"


def build_source_snapshot(db: Session, investigation_id: str, source_type: str, source_id: str) -> dict[str, Any] | None:
    """Return a traceable snapshot of a source record, or None if it is missing."""
    if source_type == "INVESTIGATOR_NOTE":
        text = (source_id or "").strip()
        if not text:
            return None
        return {
            "source_type": source_type,
            "source_id": text[:120],
            "title": "Investigator observation",
            "subtitle": text[:160],
            "date": None,
            "verification_status": "UNVERIFIED",
            "original_reference": "Manual investigator note",
            "details": {"note": text},
            "source_available": True,
        }

    if source_type == "EVIDENCE_DOCUMENT":
        item = db.get(EvidenceRecord, source_id)
        if not item or item.investigation_id != investigation_id:
            return None
        return {
            "source_type": source_type,
            "source_id": item.id,
            "title": item.filename,
            "subtitle": f"{item.format.upper()} · {item.category or 'Other'}",
            "date": item.uploaded_at.isoformat() if item.uploaded_at else None,
            "verification_status": item.status.upper(),
            "original_reference": f"Evidence Vault document {item.id} (sha256 {item.checksum[:12]}…)",
            "details": {
                "filename": item.filename,
                "format": item.format,
                "category": item.category,
                "status": item.status,
                "record_count": item.record_count,
                "checksum": item.checksum,
                "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
            },
            "source_available": True,
        }

    if source_type == "EXTRACTED_RECORD":
        found = _find_extracted_record(db, investigation_id, source_id)
        if not found:
            return None
        evidence, row = found
        verification = str(row.get("verification_status") or "PENDING").upper()
        date_value = row.get("event_date")
        date_text = date_value.get("normalized") if isinstance(date_value, dict) else date_value
        return {
            "source_type": source_type,
            "source_id": source_id,
            "title": _event_title(row),
            "subtitle": f"Extracted record · {evidence.filename}",
            "date": str(date_text) if date_text else None,
            "verification_status": verification,
            "original_reference": (
                f"{evidence.id} · record {source_id}"
                + (f" · row {row.get('source_row')}" if row.get("source_row") else "")
                + (f" · page {row.get('source_page')}" if row.get("source_page") else "")
            ),
            "details": {
                "source_evidence_id": evidence.id,
                "person_id": row.get("person_id"),
                "event_date": date_text,
                "location_id": row.get("location_id") or row.get("location"),
                "contact_person_id": row.get("contact_person_id"),
                "verification_status": verification,
                "source_row": row.get("source_row"),
                "source_page": row.get("source_page"),
                "extraction_method": row.get("extraction_method"),
                "description": row.get("description"),
                "original_data": row.get("original_data"),
                "record_id": source_id,
            },
            "source_available": True,
        }

    if source_type == "RECONSTRUCTED_EVENT":
        item = db.scalar(select(ReconstructedEvent).where(
            ReconstructedEvent.event_id == source_id,
            ReconstructedEvent.investigation_id == investigation_id,
        ))
        if not item:
            return None
        return {
            "source_type": source_type,
            "source_id": item.event_id,
            "title": item.event_description,
            "subtitle": f"{item.event_type} · {item.person_id or 'unidentified person'}",
            "date": item.event_date.isoformat() if item.event_date else None,
            "verification_status": item.verification_status,
            "original_reference": f"Reconstructed timeline event {item.event_id}",
            "details": {
                "event_type": item.event_type,
                "person_id": item.person_id,
                "event_date": item.event_date.isoformat() if item.event_date else None,
                "event_end_date": item.event_end_date.isoformat() if item.event_end_date else None,
                "date_precision": item.date_precision,
                "location_id": item.location_id,
                "location_name": item.location_name,
                "temporal_status": item.temporal_status,
                "verification_status": item.verification_status,
                "original_date_value": item.original_date_value,
            },
            "source_available": True,
        }

    if source_type == "GRAPH_RELATIONSHIP":
        item = db.scalar(select(GraphRelationship).where(
            GraphRelationship.relationship_id == source_id,
            GraphRelationship.investigation_id == investigation_id,
        ))
        if not item:
            return None
        source_node = db.get(GraphNode, item.source_node_id)
        target_node = db.get(GraphNode, item.target_node_id)
        source_label = source_node.display_label if source_node else item.source_node_id
        target_label = target_node.display_label if target_node else item.target_node_id
        return {
            "source_type": source_type,
            "source_id": item.relationship_id,
            "title": f"{source_label} → {target_label}",
            "subtitle": f"{item.relationship_type} · {item.relationship_classification}",
            "date": item.start_date.isoformat() if item.start_date else None,
            "verification_status": item.verification_status,
            "original_reference": f"Case Network relationship {item.relationship_id}",
            "details": {
                "relationship_type": item.relationship_type,
                "classification": item.relationship_classification,
                "confidence": item.confidence,
                "derivation_method": item.derivation_method,
                "explanation": item.explanation,
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "end_date": item.end_date.isoformat() if item.end_date else None,
                "verification_status": item.verification_status,
                "source_node_id": item.source_node_id,
                "target_node_id": item.target_node_id,
                "source_label": source_label,
                "target_label": target_label,
            },
            "source_available": True,
        }

    if source_type == "CONTRADICTION":
        item = db.scalar(select(Contradiction).where(
            Contradiction.contradiction_id == source_id,
            Contradiction.investigation_id == investigation_id,
        ))
        if not item:
            return None
        from ...models import ContradictionComparison
        comparisons = db.scalars(select(ContradictionComparison).where(
            ContradictionComparison.contradiction_id == item.contradiction_id
        )).all()
        return {
            "source_type": source_type,
            "source_id": item.contradiction_id,
            "title": item.title,
            "subtitle": f"{item.contradiction_type} · {item.severity} · {item.status}",
            "date": item.last_detected_at.isoformat() if item.last_detected_at else None,
            "verification_status": item.status,
            "original_reference": f"Contradiction Center finding {item.contradiction_id}",
            "details": {
                "contradiction_type": item.contradiction_type,
                "severity": item.severity,
                "status": item.status,
                "summary": item.summary,
                "explanation": item.explanation,
                "suggested_action": item.suggested_action,
                "affected_entity_id": item.affected_entity_id,
                "affected_event_id": item.affected_event_id,
                "affected_relationship_id": item.affected_relationship_id,
                "comparison_count": len(comparisons),
            },
            "source_available": True,
        }

    if source_type == "TEMPORAL_FINDING":
        item = db.scalar(select(TemporalFinding).where(
            TemporalFinding.finding_id == source_id,
            TemporalFinding.investigation_id == investigation_id,
        ))
        if not item:
            return None
        return {
            "source_type": source_type,
            "source_id": item.finding_id,
            "title": item.finding_type.replace("_", " ").title(),
            "subtitle": f"{item.severity} · {item.review_status}",
            "date": item.created_at.isoformat() if item.created_at else None,
            "verification_status": item.review_status,
            "original_reference": f"Temporal finding {item.finding_id}",
            "details": {
                "finding_type": item.finding_type,
                "severity": item.severity,
                "description": item.description,
                "review_status": item.review_status,
                "event_id": item.event_id,
                "related_event_id": item.related_event_id,
            },
            "source_available": True,
        }

    return None


def source_exists(db: Session, investigation_id: str, source_type: str, source_id: str) -> bool:
    return build_source_snapshot(db, investigation_id, source_type, source_id) is not None


def build_source_catalog(
    db: Session,
    investigation_id: str,
    source_type: str | None = None,
    q: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """List available investigation sources with assessment suggestions."""
    source_type = (source_type or "").upper() or None
    raw: list[dict[str, Any]] = []

    if source_type in {None, "EVIDENCE_DOCUMENT"}:
        for item in db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all():
            snapshot = build_source_snapshot(db, investigation_id, "EVIDENCE_DOCUMENT", item.id)
            if snapshot:
                raw.append(snapshot)
    if source_type in {None, "EXTRACTED_RECORD"}:
        for evidence in db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all():
            for row in _record_rows(evidence):
                record_id = str(row.get("record_id") or "")
                if record_id:
                    snapshot = build_source_snapshot(db, investigation_id, "EXTRACTED_RECORD", record_id)
                    if snapshot:
                        raw.append(snapshot)
    if source_type in {None, "RECONSTRUCTED_EVENT"}:
        for item in db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all():
            snapshot = build_source_snapshot(db, investigation_id, "RECONSTRUCTED_EVENT", item.event_id)
            if snapshot:
                raw.append(snapshot)
    if source_type in {None, "GRAPH_RELATIONSHIP"}:
        for item in db.scalars(select(GraphRelationship).where(GraphRelationship.investigation_id == investigation_id)).all():
            snapshot = build_source_snapshot(db, investigation_id, "GRAPH_RELATIONSHIP", item.relationship_id)
            if snapshot:
                raw.append(snapshot)
    if source_type in {None, "CONTRADICTION"}:
        for item in db.scalars(select(Contradiction).where(Contradiction.investigation_id == investigation_id)).all():
            snapshot = build_source_snapshot(db, investigation_id, "CONTRADICTION", item.contradiction_id)
            if snapshot:
                raw.append(snapshot)
    if source_type in {None, "TEMPORAL_FINDING"}:
        for item in db.scalars(select(TemporalFinding).where(TemporalFinding.investigation_id == investigation_id)).all():
            snapshot = build_source_snapshot(db, investigation_id, "TEMPORAL_FINDING", item.finding_id)
            if snapshot:
                raw.append(snapshot)

    # Show the record types investigators usually link first. Sorting before the
    # limit guarantees that one large source type cannot crowd every other type
    # out of a truncated catalogue response.
    type_order = {
        "EXTRACTED_RECORD": 0,
        "EVIDENCE_DOCUMENT": 1,
        "RECONSTRUCTED_EVENT": 2,
        "GRAPH_RELATIONSHIP": 3,
        "TEMPORAL_FINDING": 4,
        "CONTRADICTION": 5,
    }
    raw.sort(key=lambda item: item.get("title") or "")
    raw.sort(key=lambda item: (item.get("date") or "", item.get("source_id") or ""))
    raw.sort(key=lambda item: type_order.get(item.get("source_type", ""), 99))

    search = (q or "").strip().lower()
    results: list[dict[str, Any]] = []
    per_type_cap = max(1, limit // len(type_order)) if source_type is None else limit
    type_counts: dict[str, int] = {}
    for snapshot in raw:
        haystack = f"{snapshot.get('title')} {snapshot.get('subtitle')} {snapshot.get('source_id')} {json.dumps(snapshot.get('details'), default=str)}".lower()
        if search and search not in haystack:
            continue
        current_type = snapshot.get("source_type", "")
        if type_counts.get(current_type, 0) >= per_type_cap:
            continue
        strength, strength_reason, strength_considerations = suggest_strength(snapshot)
        reliability, reliability_reason, reliability_considerations = suggest_reliability(snapshot)
        type_counts[current_type] = type_counts.get(current_type, 0) + 1
        results.append({
            **snapshot,
            "suggested_strength": strength,
            "suggested_strength_reason": strength_reason,
            "strength_considerations": strength_considerations,
            "suggested_reliability": reliability,
            "suggested_reliability_reason": reliability_reason,
            "reliability_considerations": reliability_considerations,
        })
        if len(results) >= limit:
            break
    return results
