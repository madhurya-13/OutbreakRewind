"""Deterministic temporal evidence reconstruction services."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    EventAudit,
    EventSource,
    EvidenceRecord,
    ReconstructedEvent,
    TemporalFinding,
    TemporalRelationship,
    TimelineSnapshot,
)

EVENT_TAXONOMY = {
    "SYMPTOM_ONSET", "SYMPTOM_REPORTED", "CASE_IDENTIFIED", "CASE_REGISTERED",
    "RECOVERY", "HOSPITALIZATION", "DISCHARGE", "DEATH", "CONTACT_REPORTED",
    "CONTACT_OCCURRED", "SUSPECTED_EXPOSURE", "LOCATION_VISIT", "SHARED_LOCATION_EXPOSURE",
    "SAMPLE_COLLECTED", "TEST_REQUESTED", "TEST_CONDUCTED", "TEST_RESULT_RECORDED",
    "LAB_CONFIRMATION", "EVIDENCE_UPLOADED", "INVESTIGATION_CREATED", "RECORD_UPDATED",
    "EXPOSURE_DATE_REVISED", "INVESTIGATOR_OBSERVATION", "UNKNOWN_EVENT",
}

FIELD_EVENT_TYPES = {
    "symptom_start_date": "SYMPTOM_ONSET", "symptom_onset": "SYMPTOM_ONSET",
    "symptom_date": "SYMPTOM_ONSET", "exposure_date": "SUSPECTED_EXPOSURE",
    "contact_date": "CONTACT_OCCURRED", "contact_occurred": "CONTACT_OCCURRED",
    "contact_date_2": "CONTACT_OCCURRED", "contact_date_3": "CONTACT_OCCURRED",
    "visit_date": "LOCATION_VISIT", "location_visit_date": "LOCATION_VISIT",
    "collection_date": "SAMPLE_COLLECTED", "sample_date": "SAMPLE_COLLECTED",
    "test_requested_date": "TEST_REQUESTED", "test_date": "TEST_CONDUCTED",
    "result_date": "TEST_RESULT_RECORDED", "confirmation_date": "LAB_CONFIRMATION",
    "recovery_date": "RECOVERY", "hospitalization_date": "HOSPITALIZATION",
    "discharge_date": "DISCHARGE", "death_date": "DEATH",
    "reported_date": "SYMPTOM_REPORTED", "event_date": "UNKNOWN_EVENT",
}
KEYWORD_EVENT_TYPES = (
    (("symptom", "onset"), "SYMPTOM_ONSET"),
    (("symptom", "reported"), "SYMPTOM_REPORTED"),
    (("exposure",), "SUSPECTED_EXPOSURE"),
    (("contact",), "CONTACT_REPORTED"),
    (("hospital",), "HOSPITALIZATION"),
    (("discharge",), "DISCHARGE"),
    (("recovery",), "RECOVERY"),
    (("sample", "collect"), "SAMPLE_COLLECTED"),
    (("confirm",), "LAB_CONFIRMATION"),
    (("test",), "TEST_CONDUCTED"),
    (("visit",), "LOCATION_VISIT"),
)


@dataclass(frozen=True)
class DateInterpretation:
    start: date | None
    end: date | None
    precision: str
    confidence: float
    original: str | None
    interpretation: str | None
    status: str


def interpret_date(value: Any) -> DateInterpretation:
    if value is None or not str(value).strip():
        return DateInterpretation(None, None, "UNKNOWN", 0.0, None, None, "UNRESOLVED")
    original = str(value).strip()
    text = original.replace("–", "-").replace("—", "-")
    iso_timestamp = re.fullmatch(r"\d{4}-\d{2}-\d{2}T[^ ]+", text)
    if iso_timestamp:
        text = text[:10]
    slash = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash:
        first, second = (int(part) for part in slash.groups()[:2])
        if first <= 12 and second <= 12:
            return DateInterpretation(None, None, "AMBIGUOUS", 0.25, original, "DD/MM/YYYY or MM/DD/YYYY", "REQUIRES_REVIEW")
    for fmt, precision, interpretation in (
        ("%Y-%m-%d", "DAY", "ISO 8601"),
        ("%Y-%m-%d %H:%M:%S", "DAY", "ISO timestamp"),
        ("%d/%m/%Y", "DAY", "DD/MM/YYYY"),
        ("%m/%d/%Y", "DAY", "MM/DD/YYYY"),
    ):
        try:
            parsed = datetime.strptime(text, fmt).date()
            return DateInterpretation(parsed, parsed, precision, 0.98, original, interpretation, "NORMAL")
        except ValueError:
            pass
    month = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", text)
    if month:
        try:
            parsed = datetime.strptime(f"{month.group(1)} {month.group(2)}", "%B %Y").date()
        except ValueError:
            try:
                parsed = datetime.strptime(f"{month.group(1)} {month.group(2)}", "%b %Y").date()
            except ValueError:
                parsed = None
        if parsed:
            next_month = parsed.replace(day=28) + timedelta(days=4)
            end = next_month - timedelta(days=next_month.day)
            return DateInterpretation(parsed, end, "MONTH", 0.8, original, "Month YYYY", "REQUIRES_REVIEW")
    if re.fullmatch(r"\d{4}", text):
        parsed = date(int(text), 1, 1)
        return DateInterpretation(parsed, date(int(text), 12, 31), "YEAR", 0.7, original, "YYYY", "REQUIRES_REVIEW")
    approximate = re.fullmatch(r"(early|mid|late)\s+([A-Za-z]+)\s+(\d{4})", text, re.IGNORECASE)
    if approximate:
        month_value = interpret_date(f"{approximate.group(2)} {approximate.group(3)}")
        if month_value.start:
            start, end = month_value.start, month_value.end or month_value.start
            if approximate.group(1).lower() == "early":
                end = min(start + timedelta(days=9), month_value.end or end)
            elif approximate.group(1).lower() == "late":
                start = max(start, (month_value.end or start) - timedelta(days=9))
            return DateInterpretation(start, end, "APPROXIMATE", 0.55, original, "Approximate month", "REQUIRES_REVIEW")
    range_match = re.fullmatch(r"(.+?)\s+(?:to|-)\s+(.+)", text, re.IGNORECASE)
    if range_match:
        left, right = interpret_date(range_match.group(1))
        right_value = interpret_date(range_match.group(2))
        if left.start and right_value.start:
            return DateInterpretation(left.start, right_value.end or right_value.start, "RANGE", 0.7, original, "Date range", "REQUIRES_REVIEW")
    return DateInterpretation(None, None, "UNKNOWN", 0.0, original, None, "UNRESOLVED")


def _clean_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _field_value(record: dict[str, Any], names: set[str]) -> tuple[str | None, Any]:
    for key, value in record.items():
        if _clean_key(key) in names:
            return _clean_key(key), value
    return None, None


def classify_event(record: dict[str, Any], source_field: str | None = None) -> tuple[str, float]:
    keys = {_clean_key(key) for key in record}
    if source_field and _clean_key(source_field) in FIELD_EVENT_TYPES:
        return FIELD_EVENT_TYPES[_clean_key(source_field)], 0.98
    for key in keys:
        if key in FIELD_EVENT_TYPES:
            return FIELD_EVENT_TYPES[key], 0.95
    text = " ".join(str(value) for value in record.values() if value is not None).lower()
    for keywords, event_type in KEYWORD_EVENT_TYPES:
        if all(keyword in text for keyword in keywords):
            return event_type, 0.65
    return "UNKNOWN_EVENT", 0.2


def extract_candidates(evidence: EvidenceRecord) -> list[dict[str, Any]]:
    candidates = []
    for record in json.loads(evidence.records_json):
        record = dict(record)
        person_key, person = _field_value(record, {"person_id", "patient_id", "individual_id", "case_id", "subject_id"})
        location_key, location = _field_value(record, {"location_id", "location", "place", "site", "facility"})
        description_key, description = _field_value(record, {"event_description", "description", "text", "summary", "event"})
        report_key, report_value = _field_value(record, {"report_date", "reported_date", "recorded_at"})
        date_fields = [(key, value) for key, value in record.items() if _clean_key(key) in FIELD_EVENT_TYPES]
        if not date_fields:
            date_fields = [(None, record.get("event_date") or record.get("date"))]
        for field, value in date_fields:
            event_type, confidence = classify_event(record, field)
            candidates.append({
                "record": record, "person_id": str(person) if person is not None else None,
                "location_id": str(location) if location_key == "location_id" and location is not None else None,
                "location_name": str(location) if location is not None else None,
                "description": str(description or event_type.replace("_", " ").title()),
                "date_field": field, "date_value": value, "report_value": report_value,
                "event_type": event_type, "classification_confidence": confidence,
                "source_field": field or description_key or report_key,
                "source_page": record.get("source_page") or record.get("page"),
                "source_row": record.get("source_row") or record.get("_source_row"),
                "record_id": record.get("record_id"),
                "extraction_method": record.get("extraction_method", "structured_parser"),
            })
    return candidates


def _event_key(investigation_id: str, candidate: dict[str, Any], interpreted: DateInterpretation) -> str:
    raw = "|".join(str(candidate.get(key) or "") for key in ("person_id", "event_type", "location_id", "location_name"))
    return hashlib.sha256(f"{investigation_id}|{raw}|{interpreted.start}|{interpreted.end}|{candidate.get('description')}".encode()).hexdigest()


def _event_dict(event: ReconstructedEvent, sources: list[EventSource] | None = None) -> dict[str, Any]:
    result = {column.name: getattr(event, column.name) for column in event.__table__.columns}
    result["event_date"] = event.event_date.isoformat() if event.event_date else None
    result["event_end_date"] = event.event_end_date.isoformat() if event.event_end_date else None
    result["report_date"] = event.report_date.isoformat() if event.report_date else None
    result["recorded_at"] = event.recorded_at.isoformat()
    result["created_at"] = event.created_at.isoformat()
    result["updated_at"] = event.updated_at.isoformat()
    if sources is not None:
        result["sources"] = [
            {column.name: getattr(source, column.name) for column in source.__table__.columns}
            for source in sources
        ]
    return result


def _relationship(left: ReconstructedEvent, right: ReconstructedEvent) -> tuple[str, str]:
    if not left.event_date or not right.event_date:
        return "UNKNOWN", "INDETERMINATE"
    left_end = left.event_end_date or left.event_date
    right_end = right.event_end_date or right.event_date
    if left_end < right.event_date:
        return "BEFORE", "DEFINITE"
    if right_end < left.event_date:
        return "AFTER", "DEFINITE"
    if left.event_date == right.event_date and left_end == right_end:
        return "EQUALS", "DEFINITE"
    return "OVERLAPS", "POTENTIAL"


def _add_finding(db: Session, investigation_id: str, event_id: str | None, related_id: str | None, finding_type: str, severity: str, description: str) -> None:
    fingerprint = f"{investigation_id}|{event_id}|{related_id}|{finding_type}"
    finding_id = f"FND-{hashlib.sha1(fingerprint.encode()).hexdigest()[:12].upper()}"
    db.add(TemporalFinding(
        finding_id=finding_id, investigation_id=investigation_id, event_id=event_id,
        related_event_id=related_id, finding_type=finding_type, severity=severity,
        description=description, review_status="UNRESOLVED", created_at=datetime.now(timezone.utc),
    ))


def reconstruct_timeline(investigation_id: str, db: Session) -> dict[str, Any]:
    evidence_items = list(db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all())
    candidates = []
    for item in evidence_items:
        for candidate in extract_candidates(item):
            candidate["evidence_id"] = item.id
            candidates.append(candidate)
    now = datetime.now(timezone.utc)
    existing = {event.event_id: event for event in db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all()}
    source_keys = {(source.event_id, source.evidence_id, source.extracted_record_id) for source in db.scalars(select(EventSource)).all()}
    for candidate in candidates:
        interpreted = interpret_date(candidate["date_value"])
        key = _event_key(investigation_id, candidate, interpreted)
        event_id = f"EVT-{key[:12].upper()}"
        event = existing.get(event_id)
        if event is None:
            event = ReconstructedEvent(
                event_id=event_id, investigation_id=investigation_id, person_id=candidate["person_id"],
                event_type=candidate["event_type"], event_description=candidate["description"],
                event_date=interpreted.start, event_end_date=interpreted.end, date_precision=interpreted.precision,
                date_confidence=interpreted.confidence, original_date_value=interpreted.original,
                date_interpretation=interpreted.interpretation, report_date=interpret_date(candidate["report_value"]).start,
                recorded_at=now, location_id=candidate["location_id"], location_name=candidate["location_name"],
                temporal_status=interpreted.status if interpreted.status != "NORMAL" else "NORMAL",
                verification_status="PENDING", classification_confidence=candidate["classification_confidence"],
                created_at=now, updated_at=now,
            )
            db.add(event)
            db.flush()
            existing[event_id] = event
        source_key = (event_id, candidate["evidence_id"], candidate["record_id"])
        if source_key not in source_keys:
            source = EventSource(
                event_id=event_id, evidence_id=candidate["evidence_id"], extracted_record_id=candidate["record_id"],
                source_page=candidate["source_page"], source_row=candidate["source_row"],
                source_field=candidate["source_field"], original_value=str(candidate["date_value"]) if candidate["date_value"] is not None else None,
                extraction_method=candidate["extraction_method"],
            )
            db.add(source)
            source_keys.add(source_key)
    db.flush()
    events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all())
    db.execute(delete(TemporalFinding).where(TemporalFinding.investigation_id == investigation_id))
    db.execute(delete(TemporalRelationship).where(TemporalRelationship.event_id.in_([event.event_id for event in events])))
    for event in events:
        if event.temporal_status != "NORMAL":
            _add_finding(db, investigation_id, event.event_id, None, "UNCERTAIN_DATE", "REQUIRES_REVIEW", "Event date is incomplete or ambiguous and requires review.")
        if event.event_type == "UNKNOWN_EVENT":
            _add_finding(db, investigation_id, event.event_id, None, "UNKNOWN_EVENT", "REQUIRES_REVIEW", "The event could not be classified reliably.")
    for index, left in enumerate(events):
        for right in events[index + 1:]:
            relationship_type, certainty = _relationship(left, right)
            db.add(TemporalRelationship(
                relationship_id=f"REL-{uuid.uuid4().hex[:12].upper()}", event_id=left.event_id,
                related_event_id=right.event_id, relationship_type=relationship_type,
                temporal_certainty=certainty, created_at=now,
            ))
            if left.person_id and left.person_id == right.person_id:
                if (
                    left.event_type == right.event_type
                    and left.event_date == right.event_date
                    and left.location_name == right.location_name
                    and left.event_id != right.event_id
                ):
                    _add_finding(db, investigation_id, left.event_id, right.event_id, "POTENTIAL_DUPLICATE", "WARNING", "Events share the same person, type, date, and location and may be duplicates.")
                pair = {left.event_type, right.event_type}
                if pair == {"SUSPECTED_EXPOSURE", "SYMPTOM_ONSET"}:
                    exposure, onset = (left, right) if left.event_type == "SUSPECTED_EXPOSURE" else (right, left)
                    if exposure.event_date and onset.event_date and exposure.event_date > onset.event_date:
                        _add_finding(db, investigation_id, exposure.event_id, onset.event_id, "EXPOSURE_AFTER_ONSET", "WARNING", "Potential temporal inconsistency: exposure occurs after symptom onset.")
                if pair == {"LAB_CONFIRMATION", "SAMPLE_COLLECTED"}:
                    confirmation, sample = (left, right) if left.event_type == "LAB_CONFIRMATION" else (right, left)
                    if confirmation.event_date and sample.event_date and confirmation.event_date < sample.event_date:
                        _add_finding(db, investigation_id, confirmation.event_id, sample.event_id, "CONFIRMATION_BEFORE_SAMPLE", "REQUIRES_REVIEW", "Laboratory confirmation predates sample collection.")
                if pair == {"RECOVERY", "SYMPTOM_ONSET"}:
                    recovery, onset = (left, right) if left.event_type == "RECOVERY" else (right, left)
                    if recovery.event_date and onset.event_date and recovery.event_date < onset.event_date:
                        _add_finding(db, investigation_id, recovery.event_id, onset.event_id, "RECOVERY_BEFORE_ONSET", "REQUIRES_REVIEW", "Recovery predates reported symptom onset.")
    version = (db.scalar(select(TimelineSnapshot.version_number).where(TimelineSnapshot.investigation_id == investigation_id).order_by(TimelineSnapshot.version_number.desc())) or 0) + 1
    db.add(TimelineSnapshot(
        snapshot_id=f"SNAP-{uuid.uuid4().hex[:12].upper()}", investigation_id=investigation_id,
        version_number=version, event_count=len(events), generated_at=now,
        reconstruction_metadata=json.dumps({"source_evidence": len(evidence_items), "candidate_events": len(candidates)}),
    ))
    db.commit()
    return {"investigation_id": investigation_id, "version_number": version, "event_count": len(events), "source_evidence_count": len(evidence_items)}


def event_to_dict(db: Session, event: ReconstructedEvent) -> dict[str, Any]:
    sources = list(db.scalars(select(EventSource).where(EventSource.event_id == event.event_id)).all())
    return _event_dict(event, sources)
