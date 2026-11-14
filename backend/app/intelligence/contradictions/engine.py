"""Deterministic, evidence-backed contradiction detection."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import (
    Contradiction, ContradictionComparison, ContradictionEvidence, ContradictionReview,
    ContradictionSnapshot, EvidenceRecord, EventSource, GraphRelationship,
    ReconstructedEvent, TemporalFinding,
)
from ...temporal_engine import interpret_date

STATUSES = {"DETECTED", "UNDER_REVIEW", "CONFIRMED_CONFLICT", "RESOLVED", "DISMISSED", "REOPENED"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}

def _value(value: Any) -> str:
    return "" if value is None else str(value)

def _record_value(record: dict[str, Any], names: set[str]) -> tuple[str | None, Any]:
    for key, value in record.items():
        if str(key).strip().lower().replace(" ", "_") in names:
            return str(key), value
    return None, None

def _fingerprint(investigation_id: str, kind: str, entity: str, event: str | None, rule: str, values: list[str]) -> str:
    raw = "|".join([investigation_id, kind, entity, event or "", rule, *sorted(values)])
    return f"CON-{hashlib.sha256(raw.encode()).hexdigest()[:20].upper()}"

def _severity(kind: str) -> tuple[str, str]:
    if kind in {"SAMPLE_OWNER_CONFLICT", "LAB_RESULT_CONFLICT", "PERSON_ID_CONFLICT"}:
        return "HIGH", "The conflict affects a laboratory identifier or stable person reference."
    if kind in {"DATE_CONFLICT", "LOCATION_CONFLICT", "CONTACT_CONFLICT", "EVENT_ORDER_CONFLICT"}:
        return "HIGH", "The conflict changes interpretation of an event or documented relationship."
    if kind.startswith("MISSING_"):
        return "LOW", "Required information is incomplete, so the record cannot be fully validated."
    return "MEDIUM", "The conflicting source values require investigator review."

def _make_candidate(kind: str, title: str, entity: str, event_id: str | None, rule: str,
                    field: str, source_a: dict[str, Any], source_b: dict[str, Any],
                    affected_type: str, summary: str) -> dict[str, Any]:
    severity, reason = _severity(kind)
    return {
        "id": _fingerprint(source_a["investigation_id"], kind, entity, event_id, rule, [source_a["value"], source_b["value"]]),
        "investigation_id": source_a["investigation_id"], "contradiction_type": kind, "title": title,
        "summary": summary, "severity": severity, "machine_priority": reason, "affected_entity_type": affected_type,
        "affected_entity_id": entity, "affected_event_id": event_id, "detection_rule": rule,
        "explanation": f"{summary} Source A reports {source_a['value']!r}; Source B reports {source_b['value']!r}. "
                       f"Both values were compared using the rule {rule}. This difference is not proof that either source is false.",
        "suggested_action": "Inspect the original source documents and determine whether the values represent different fields, reporting delays, or a genuine conflict.",
        "field": field, "source_a": source_a, "source_b": source_b,
    }

def _persist_candidate(db: Session, candidate: dict[str, Any], now: datetime) -> tuple[Contradiction, bool]:
    contradiction = db.get(Contradiction, candidate["id"])
    new = contradiction is None
    if new:
        contradiction = Contradiction(
            contradiction_id=candidate["id"], investigation_id=candidate["investigation_id"],
            contradiction_type=candidate["contradiction_type"], title=candidate["title"],
            summary=candidate["summary"], severity=candidate["severity"], machine_priority=candidate["machine_priority"],
            affected_entity_type=candidate["affected_entity_type"], affected_entity_id=candidate["affected_entity_id"],
            affected_event_id=candidate["affected_event_id"], detection_rule=candidate["detection_rule"],
            explanation=candidate["explanation"], suggested_action=candidate["suggested_action"], status="DETECTED",
            first_detected_at=now, last_detected_at=now, created_at=now, updated_at=now,
        )
        db.add(contradiction)
        db.flush()
    else:
        contradiction.last_detected_at = now
        contradiction.updated_at = now
        if contradiction.status in {"RESOLVED", "DISMISSED"}:
            previous_status = contradiction.status
            contradiction.status = "REOPENED"
            db.add(ContradictionReview(
                review_id=f"CR-{uuid.uuid4().hex[:16].upper()}", contradiction_id=contradiction.contradiction_id,
                reviewer="system", action="REOPENED", review_note="New or changed evidence was detected.",
                previous_status=previous_status,
                new_status="REOPENED", created_at=now,
            ))
    existing = db.scalar(select(ContradictionComparison).where(
        ContradictionComparison.contradiction_id == contradiction.contradiction_id,
        ContradictionComparison.field_name == candidate["field"],
        ContradictionComparison.source_a_value == candidate["source_a"]["value"],
        ContradictionComparison.source_b_value == candidate["source_b"]["value"],
    ))
    if not existing:
        db.add(ContradictionComparison(
            contradiction_id=contradiction.contradiction_id, field_name=candidate["field"],
            source_a_value=candidate["source_a"]["value"], source_b_value=candidate["source_b"]["value"],
            normalized_a_value=candidate["source_a"].get("normalized", candidate["source_a"]["value"]),
            normalized_b_value=candidate["source_b"].get("normalized", candidate["source_b"]["value"]),
            comparison_rule=candidate["detection_rule"], comparison_result=candidate["contradiction_type"],
            explanation=candidate["explanation"],
        ))
    for role, source in (("A", candidate["source_a"]), ("B", candidate["source_b"])):
        exists = db.scalar(select(ContradictionEvidence).where(
            ContradictionEvidence.contradiction_id == contradiction.contradiction_id,
            ContradictionEvidence.evidence_id == source.get("evidence_id"),
            ContradictionEvidence.extracted_record_id == source.get("record_id"),
            ContradictionEvidence.comparison_role == role,
        ))
        if not exists:
            db.add(ContradictionEvidence(
                contradiction_id=contradiction.contradiction_id, evidence_id=source.get("evidence_id"),
                extracted_record_id=source.get("record_id"), reconstructed_event_id=source.get("event_id"),
                source_field=source.get("field"), original_value=source["value"],
                normalized_value=source.get("normalized"), source_location=source.get("location"),
                comparison_role=role,
            ))
    return contradiction, new

def detect_contradictions(investigation_id: str, db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    evidence = list(db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all())
    events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all())
    event_sources = list(db.scalars(select(EventSource).where(EventSource.event_id.in_(select(ReconstructedEvent.event_id).where(ReconstructedEvent.investigation_id == investigation_id)))).all())
    source_by_record = {(source.evidence_id, source.extracted_record_id): source for source in event_sources}
    candidates: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for item in evidence:
        for raw in json.loads(item.records_json):
            record = dict(raw)
            person = _value(record.get("person_id") or record.get("case_id") or record.get("patient_id"))
            record["_evidence_id"] = item.id
            record["_investigation_id"] = investigation_id
            record["_person_id"] = person
            records.append(record)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    sample_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        person = record["_person_id"]
        if person:
            for field in ("event_date", "contact_date", "visit_date", "location_id", "sample_id", "laboratory_result", "test_result", "result"):
                if field in record and record[field] not in (None, ""):
                    grouped[(person, field)].append(record)
            if record.get("sample_id"):
                sample_groups[_value(record["sample_id"])].append(record)
    for (person, field), values in grouped.items():
        distinct = {}
        for record in values:
            raw_value = record[field]
            if isinstance(raw_value, dict): raw_value = raw_value.get("original", raw_value)
            distinct.setdefault(_value(raw_value), record)
        if len(distinct) < 2:
            continue
        ordered = list(distinct.values())
        first, second = ordered[0], ordered[1]
        if field in {"event_date", "contact_date", "visit_date"}:
            left, right = interpret_date(first[field]), interpret_date(second[field])
            if left.start and right.start and left.start == right.start:
                continue
            kind, title = "DATE_CONFLICT", "Conflicting event dates"
            rule = "same stable person and field with distinct normalized date values"
        elif field == "location_id":
            kind, title = "LOCATION_CONFLICT", "Conflicting event locations"
            rule = "same stable person and field with distinct location identifiers"
        elif field == "sample_id":
            kind, title = "SAMPLE_OWNER_CONFLICT", "Sample identifier has conflicting ownership"
            rule = "same sample identifier associated with different stable person references"
        elif field in {"laboratory_result", "test_result", "result"}:
            kind, title = "LAB_RESULT_CONFLICT", "Conflicting laboratory results"
            rule = "same stable person and laboratory result field has distinct values"
        else:
            continue
        event_a = source_by_record.get((first["_evidence_id"], first.get("record_id")))
        event_b = source_by_record.get((second["_evidence_id"], second.get("record_id")))
        candidates.append(_make_candidate(
            kind, title, person, event_a.event_id if event_a and event_a.event_id == (event_b.event_id if event_b else None) else None,
            rule, field,
            {"investigation_id": investigation_id, "value": _value(first[field]), "normalized": _value(first[field]), "evidence_id": first["_evidence_id"], "record_id": first.get("record_id"), "event_id": event_a.event_id if event_a else None, "field": field},
            {"investigation_id": investigation_id, "value": _value(second[field]), "normalized": _value(second[field]), "evidence_id": second["_evidence_id"], "record_id": second.get("record_id"), "event_id": event_b.event_id if event_b else None, "field": field},
            "PERSON", f"Records for {person} contain incompatible {field} values.",
        ))
    for sample_id, values in sample_groups.items():
        owners = {item["_person_id"] for item in values if item["_person_id"]}
        if len(owners) > 1:
            first, second = values[0], next(item for item in values[1:] if item["_person_id"] != first["_person_id"])
            candidates.append(_make_candidate(
                "SAMPLE_OWNER_CONFLICT", "Sample identifier has conflicting ownership", sample_id, None,
                "same sample identifier is associated with different stable person references", "sample_id",
                {"investigation_id": investigation_id, "value": first["_person_id"], "normalized": first["_person_id"], "evidence_id": first["_evidence_id"], "record_id": first.get("record_id"), "field": "person_id"},
                {"investigation_id": investigation_id, "value": second["_person_id"], "normalized": second["_person_id"], "evidence_id": second["_evidence_id"], "record_id": second.get("record_id"), "field": "person_id"},
                "SAMPLE", f"Sample {sample_id} is associated with more than one person identifier.",
            ))
    for finding in db.scalars(select(TemporalFinding).where(TemporalFinding.investigation_id == investigation_id)).all():
        if finding.finding_type in {"CONFIRMATION_BEFORE_SAMPLE", "RECOVERY_BEFORE_ONSET", "EXPOSURE_AFTER_ONSET"}:
            candidates.append({
                "id": _fingerprint(investigation_id, "EVENT_ORDER_CONFLICT", finding.event_id or "", finding.related_event_id, "milestone 3 temporal finding", [""]),
                "investigation_id": investigation_id, "contradiction_type": "EVENT_ORDER_CONFLICT",
                "title": "Reconstructed events have an inconsistent order", "summary": finding.description,
                "severity": "HIGH", "machine_priority": "Milestone 3 identified an ordering inconsistency.",
                "affected_entity_type": "EVENT", "affected_entity_id": finding.event_id, "affected_event_id": finding.event_id,
                "detection_rule": "reuse temporal reconstruction finding", "explanation": finding.description,
                "suggested_action": "Review the supporting dates and confirm whether the reported fields represent distinct dates.",
                "field": "event_date", "source_a": {"investigation_id": investigation_id, "value": finding.event_id or "", "event_id": finding.event_id},
                "source_b": {"investigation_id": investigation_id, "value": finding.related_event_id or "", "event_id": finding.related_event_id},
            })
    for record in records:
        if record["_person_id"] == "" or not record.get("record_id"):
            continue
        for field, kind, title in (("event_date", "MISSING_EVENT_DATE", "Event is missing a date"), ("sample_id", "INCOMPLETE_LAB_RECORD", "Laboratory record is incomplete")):
            if field not in record or record[field] in (None, ""):
                source = {"investigation_id": investigation_id, "value": "missing", "evidence_id": record["_evidence_id"], "record_id": record.get("record_id"), "field": field}
                candidates.append(_make_candidate(kind, title, record["_person_id"], None, f"required {field} is absent", field, source, source, "PERSON", f"Record {record['record_id']} cannot be fully validated because {field} is missing."))
    new_count = updated_count = 0
    for candidate in candidates:
        _, created = _persist_candidate(db, candidate, now)
        new_count += int(created)
        updated_count += int(not created)
    existing_count = db.scalar(select(Contradiction).where(Contradiction.investigation_id == investigation_id).count()) if False else len(list(db.scalars(select(Contradiction).where(Contradiction.investigation_id == investigation_id)).all()))
    version = (db.scalar(select(ContradictionSnapshot.snapshot_version).where(ContradictionSnapshot.investigation_id == investigation_id).order_by(ContradictionSnapshot.snapshot_version.desc())) or 0) + 1
    db.add(ContradictionSnapshot(snapshot_id=f"CS-{uuid.uuid4().hex[:16].upper()}", investigation_id=investigation_id, snapshot_version=version,
                                 detected_count=existing_count, new_count=new_count, updated_count=updated_count,
                                 resolved_count=sum(1 for item in db.scalars(select(Contradiction).where(Contradiction.investigation_id == investigation_id)).all() if item.status in {"RESOLVED", "DISMISSED"}),
                                 run_timestamp=now, summary=json.dumps({"candidate_count": len(candidates)})))
    db.commit()
    return {"investigation_id": investigation_id, "snapshot_version": version, "detected_count": existing_count, "new_count": new_count, "updated_count": updated_count}

def contradiction_dict(db: Session, item: Contradiction) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["comparisons"] = [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in db.scalars(select(ContradictionComparison).where(ContradictionComparison.contradiction_id == item.contradiction_id)).all()]
    result["evidence"] = [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in db.scalars(select(ContradictionEvidence).where(ContradictionEvidence.contradiction_id == item.contradiction_id)).all()]
    result["reviews"] = [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in db.scalars(select(ContradictionReview).where(ContradictionReview.contradiction_id == item.contradiction_id).order_by(ContradictionReview.created_at.desc())).all()]
    for key in ("first_detected_at", "last_detected_at", "created_at", "updated_at"):
        result[key] = result[key].isoformat()
    return result
