from datetime import date, datetime, timezone
import json
import uuid
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import Contradiction, ContradictionReview, ContradictionSnapshot, Event, EventAudit, EventSource, EvidenceRecord, GraphRelationship, GraphNode, ReconstructedEvent, RelationshipReviewHistory, TemporalFinding, TemporalRelationship, TimelineSnapshot, Hypothesis, HypothesisAssessment, HypothesisEvidenceLink, HypothesisImpactRecord, HypothesisNote, HypothesisReviewHistory, HypothesisVersion
from .evidence import evidence_dict, ingest_upload
from .schemas import (ContradictionReviewRequest, EventCorrection, EventRead, HealthRead, RelationshipReview,
                      HypothesisCompareRequest, HypothesisCreate, HypothesisEvidenceCreate,
                      HypothesisEvidenceUpdate, HypothesisNoteCreate, HypothesisStatusUpdate,
                      HypothesisUpdate, ImpactReviewRequest)
from .intelligence.graph_service import (
    graph_metrics_from_graph, graph_payload, network_for_person, paths_for_people,
    rebuild_graph, relationship_detail,
)
from .intelligence.contradictions.engine import contradiction_dict, detect_contradictions
from .temporal_engine import EVENT_TAXONOMY, event_to_dict, reconstruct_timeline
from .intelligence.hypothesis import (
    add_note,
    analyze_source_change,
    archive_hypothesis as archive_hypothesis_service,
    assessment_dict,
    build_source_catalog,
    compare_hypotheses as compare_hypotheses_service,
    create_hypothesis as create_hypothesis_service,
    evaluate_hypothesis as evaluate_hypothesis_service,
    evaluate_investigation_hypotheses as evaluate_all_hypotheses,
    hypothesis_detail as hypothesis_detail_service,
    hypothesis_dict,
    hypothesis_history as hypothesis_history_service,
    impact_dict,
    investigation_summary,
    latest_assessment as latest_hypothesis_assessment,
    link_dict,
    link_evidence,
    list_hypotheses as list_hypotheses_service,
    list_impacts,
    list_links,
    list_notes,
    note_dict,
    review_impact,
    source_exists,
    update_hypothesis as update_hypothesis_service,
    update_link,
    update_status as update_status_service,
    withdraw_link,
)
from .intelligence.hypothesis.hypothesis_versioning import version_detail
from .intelligence.hypothesis.serializers import version_dict
from .intelligence.hypothesis.serializers import hypothesis_dict as _hypothesis_dict
from .intelligence.hypothesis.serializers import now as hypothesis_now

app = FastAPI(title="Outbreak Rewind API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SEED = [
    ("EV-042", date(2024, 6, 18), "Port Meridian transmission spike", "Port Meridian, OR", "critical", "Epidemiology", "Wastewater sampling exceeds alert threshold for the third consecutive day.", "ORION / NW-7"),
    ("EV-041", date(2024, 6, 17), "Hospital network capacity warning", "Cascadia corridor", "high", "Health systems", "Four facilities report ICU utilization above 85%; staffing shortages emerging.", "State HHS"),
    ("EV-040", date(2024, 6, 16), "Variant signal detected", "North Cascades", "high", "Genomics", "A new lineage appears in two independent sequencing runs.", "LabNet"),
    ("EV-039", date(2024, 6, 14), "School absenteeism normalizes", "Willow County", "low", "Community", "Absenteeism returns to seasonal baseline across 14 districts.", "EDU-STAT"),
    ("EV-038", date(2024, 6, 11), "Supply route disruption", "East Ridge", "medium", "Logistics", "Cold-chain deliveries delayed by 36 hours after a border closure.", "LOGOS"),
]

@app.on_event("startup")
def initialize() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if not db.scalar(select(Event.id).limit(1)):
            db.add_all(Event(id=i, date=d, title=t, location=l, severity=s, category=c, summary=sm, source=so) for i, d, t, l, s, c, sm, so in SEED)
            db.commit()

INVESTIGATIONS = [
    {"investigation_id": "ORION-001", "investigation_name": "Project Orion", "description": "A fictional respiratory outbreak investigation used exclusively for demonstrating the platform.", "outbreak_category": "Respiratory", "status": "Active", "total_cases": 124, "evidence_records": 386},
    {"investigation_id": "ORION-002", "investigation_name": "North Cascades Sentinel", "description": "Synthetic sentinel investigation for a regional signal.", "outbreak_category": "Respiratory", "status": "Review", "total_cases": 38, "evidence_records": 94},
    {"investigation_id": "ORION-003", "investigation_name": "East Ridge Cluster", "description": "Synthetic cluster reconstruction for training workflows.", "outbreak_category": "Unknown", "status": "Archived", "total_cases": 17, "evidence_records": 42},
]
EVIDENCE = [
    {"evidence_id": "EVD-001", "evidence_type": "Case report", "source": "Clinic A", "investigation_id": "ORION-001", "uploaded_at": "2024-06-18", "verification_status": "Verified"},
    {"evidence_id": "EVD-002", "evidence_type": "Laboratory record", "source": "LAB-004", "investigation_id": "ORION-001", "uploaded_at": "2024-06-17", "verification_status": "Verified"},
    {"evidence_id": "EVD-003", "evidence_type": "Contact interview", "source": "Field team 02", "investigation_id": "ORION-001", "uploaded_at": "2024-06-16", "verification_status": "Pending"},
    {"evidence_id": "EVD-004", "evidence_type": "Location record", "source": "LOC-02", "investigation_id": "ORION-001", "uploaded_at": "2024-06-15", "verification_status": "Verified"},
]

@app.get("/api/health", response_model=HealthRead)
def health(db: Session = Depends(get_db)) -> HealthRead:
    try:
        db.execute(text("SELECT 1"))
        return HealthRead(status="ok", database="connected")
    except Exception:
        return HealthRead(status="degraded", database="unavailable")

@app.get("/health", response_model=HealthRead, include_in_schema=False)
def legacy_health(db: Session = Depends(get_db)) -> HealthRead:
    return health(db)

@app.get("/api/investigations")
def investigations() -> list[dict]:
    return INVESTIGATIONS

@app.get("/api/investigations/{investigation_id}")
def investigation(investigation_id: str) -> dict:
    item = next((i for i in INVESTIGATIONS if i["investigation_id"] == investigation_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {**item, "synthetic": True, "events": SEED, "evidence": EVIDENCE}

@app.get("/api/evidence")
def evidence(db: Session = Depends(get_db), investigation_id: str | None = None, status: str | None = None) -> list[dict]:
    query = select(EvidenceRecord).order_by(EvidenceRecord.uploaded_at.desc())
    if investigation_id:
        query = query.where(EvidenceRecord.investigation_id == investigation_id)
    if status:
        query = query.where(EvidenceRecord.status == status)
    uploaded = [evidence_dict(item) for item in db.scalars(query).all()]
    return uploaded + EVIDENCE

@app.post("/api/evidence/upload")
def upload_evidence(
    files: list[UploadFile] = File(...),
    investigation_id: str = "ORION-001",
    category: str = Form("Other"),
    db: Session = Depends(get_db),
) -> dict:
    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="Upload between 1 and 20 files")
    results = []
    for upload in files:
        try:
            item = ingest_upload(upload, investigation_id, db, category)
            analyze_source_change(
                db, investigation_id, "EVIDENCE_DOCUMENT", item.id,
                trigger="EVIDENCE_UPLOADED", include_unlinked=True,
            )
            db.commit()
            results.append(evidence_dict(item))
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"items": results}

@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(EvidenceRecord, evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    result = evidence_dict(item)
    result.update({"provenance": json.loads(item.provenance), "validation_errors": json.loads(item.validation_errors)})
    return result

@app.get("/api/evidence/{evidence_id}/records")
def evidence_records(evidence_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(EvidenceRecord, evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"evidence_id": evidence_id, "records": json.loads(item.records_json)}

@app.get("/api/evidence/{evidence_id}/status")
def evidence_status(evidence_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(EvidenceRecord, evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"evidence_id": item.id, "stage": item.processing_stage, "extraction_status": item.status, "validation_status": item.status, "errors": json.loads(item.validation_errors), "completed_at": item.uploaded_at.isoformat() if item.processing_stage == "completed" else None}

@app.get("/api/evidence/{evidence_id}/source")
def evidence_source(evidence_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    item = db.get(EvidenceRecord, evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    path = (settings.storage_dir_path / item.storage_path).resolve()
    if settings.storage_dir_path not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Source document unavailable")
    return FileResponse(path, filename=item.filename, media_type="application/octet-stream")

@app.patch("/api/evidence/records/{record_id}/verify")
def verify_record(record_id: str, verified: bool = True, db: Session = Depends(get_db)) -> dict:
    matches = db.scalars(select(EvidenceRecord)).all()
    for item in matches:
        records = json.loads(item.records_json)
        for record in records:
            if record.get("record_id") == record_id:
                record["verification_status"] = "VERIFIED" if verified else "REJECTED"
                item.records_json = json.dumps(records)
                analyze_source_change(
                    db, item.investigation_id, "EXTRACTED_RECORD", record_id,
                    trigger="EXTRACTED_RECORD_VERIFIED", include_unlinked=False,
                )
                db.commit()
                return {"record_id": record_id, "verification_status": record["verification_status"]}
    raise HTTPException(status_code=404, detail="Extracted record not found")

@app.get("/api/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    active_hypotheses = db.scalar(select(func.count()).select_from(Hypothesis).where(Hypothesis.status != "ARCHIVED")) or 0
    unresolved = db.scalar(select(func.count()).select_from(Contradiction).where(
        Contradiction.status.in_(["DETECTED", "UNDER_REVIEW", "REOPENED"])
    )) or 0
    pending_hypothesis_review = db.scalar(select(func.count()).select_from(HypothesisImpactRecord).where(
        HypothesisImpactRecord.requires_review.is_(True)
    )) or 0
    return {
        "active_investigations": 8, "total_cases": 124,
        "evidence_records": db.scalar(select(func.count()).select_from(EvidenceRecord)) or 0,
        "unresolved_contradictions": unresolved,
        "active_hypotheses": active_hypotheses,
        "hypotheses_requiring_review": pending_hypothesis_review,
    }

@app.get("/api/events", response_model=list[EventRead])
def events(db: Session = Depends(get_db)) -> list[Event]:
    return list(db.scalars(select(Event).order_by(Event.date.desc())).all())


@app.post("/api/timeline/reconstruct/{investigation_id}")
def reconstruct(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    if not any(item["investigation_id"] == investigation_id for item in INVESTIGATIONS):
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        return reconstruct_timeline(investigation_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Timeline reconstruction failed") from exc


@app.get("/api/timeline/{investigation_id}")
def timeline(
    investigation_id: str,
    db: Session = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    event_type: str | None = None,
    person_id: str | None = None,
    include_unresolved: bool = True,
) -> list[dict]:
    query = select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)
    if date_from:
        query = query.where(ReconstructedEvent.event_date >= date_from)
    if date_to:
        query = query.where(ReconstructedEvent.event_date <= date_to)
    if event_type:
        query = query.where(ReconstructedEvent.event_type == event_type)
    if person_id:
        query = query.where(ReconstructedEvent.person_id == person_id)
    if not include_unresolved:
        query = query.where(ReconstructedEvent.temporal_status == "NORMAL")
    events = list(db.scalars(query).all())
    events.sort(key=lambda item: (item.event_date is None, item.event_date or date.max, item.event_id))
    return [event_to_dict(db, event) for event in events]


@app.get("/api/timeline/{investigation_id}/events/{event_id}")
def timeline_event(investigation_id: str, event_id: str, db: Session = Depends(get_db)) -> dict:
    event = db.scalar(select(ReconstructedEvent).where(
        ReconstructedEvent.investigation_id == investigation_id,
        ReconstructedEvent.event_id == event_id,
    ))
    if not event:
        raise HTTPException(status_code=404, detail="Reconstructed event not found")
    return event_to_dict(db, event)


@app.get("/api/timeline/{investigation_id}/findings")
def timeline_findings(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    findings = db.scalars(select(TemporalFinding).where(TemporalFinding.investigation_id == investigation_id).order_by(TemporalFinding.created_at.desc())).all()
    return [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in findings]


@app.get("/api/timeline/{investigation_id}/relationships")
def timeline_relationships(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    event_ids = select(ReconstructedEvent.event_id).where(ReconstructedEvent.investigation_id == investigation_id)
    relationships = db.scalars(select(TemporalRelationship).where(TemporalRelationship.event_id.in_(event_ids))).all()
    return [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in relationships]


@app.get("/api/timeline/{investigation_id}/snapshots")
def timeline_snapshots(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    snapshots = db.scalars(select(TimelineSnapshot).where(TimelineSnapshot.investigation_id == investigation_id).order_by(TimelineSnapshot.version_number.desc())).all()
    return [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in snapshots]


@app.get("/api/timeline/{investigation_id}/statistics")
def timeline_statistics(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all())
    findings = list(db.scalars(select(TemporalFinding).where(TemporalFinding.investigation_id == investigation_id)).all())
    return {
        "total_events": len(events),
        "identified_event_types": sorted({event.event_type for event in events}),
        "exact_dates": sum(event.date_precision == "DAY" for event in events),
        "approximate_dates": sum(event.date_precision in {"MONTH", "YEAR", "APPROXIMATE", "RANGE"} for event in events),
        "events_requiring_review": sum(event.temporal_status == "REQUIRES_REVIEW" for event in events),
        "unresolved_dates": sum(event.date_precision in {"UNKNOWN", "AMBIGUOUS"} for event in events),
        "potential_duplicate_groups": sum(item.finding_type == "POTENTIAL_DUPLICATE" for item in findings),
        "temporal_findings": len(findings),
    }


@app.get("/api/timeline/{investigation_id}/persons/{person_id}")
def person_timeline(investigation_id: str, person_id: str, db: Session = Depends(get_db)) -> list[dict]:
    events = db.scalars(select(ReconstructedEvent).where(
        ReconstructedEvent.investigation_id == investigation_id,
        ReconstructedEvent.person_id == person_id,
    )).all()
    return [event_to_dict(db, event) for event in sorted(events, key=lambda item: (item.event_date is None, item.event_date or date.max, item.event_id))]


@app.get("/api/timeline/{investigation_id}/sources/{event_id}")
def timeline_sources(investigation_id: str, event_id: str, db: Session = Depends(get_db)) -> list[dict]:
    event = db.scalar(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id, ReconstructedEvent.event_id == event_id))
    if not event:
        raise HTTPException(status_code=404, detail="Reconstructed event not found")
    sources = db.scalars(select(EventSource).where(EventSource.event_id == event_id)).all()
    return [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in sources]


@app.post("/api/timeline/events/{event_id}/verify")
def verify_timeline_event(event_id: str, verified: bool = True, db: Session = Depends(get_db)) -> dict:
    event = db.get(ReconstructedEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Reconstructed event not found")
    event.verification_status = "VERIFIED" if verified else "REJECTED"
    event.updated_at = datetime.now(timezone.utc)
    analyze_source_change(
        db, event.investigation_id, "RECONSTRUCTED_EVENT", event_id,
        trigger="TIMELINE_EVENT_VERIFIED", include_unlinked=False,
    )
    db.commit()
    return {"event_id": event_id, "verification_status": event.verification_status}


@app.patch("/api/timeline/events/{event_id}")
def correct_timeline_event(event_id: str, changes: EventCorrection, db: Session = Depends(get_db)) -> dict:
    event = db.get(ReconstructedEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Reconstructed event not found")
    payload = changes.model_dump(exclude_unset=True)
    actor = str(payload.pop("actor", "investigator"))
    allowed = {"event_description", "event_type", "person_id", "location_id", "location_name", "event_date", "event_end_date", "temporal_status"}
    update = {key: value for key, value in payload.items() if key in allowed}
    if not update:
        raise HTTPException(status_code=422, detail="No correctable event fields supplied")
    previous = {key: getattr(event, key) for key in update}
    for key, value in update.items():
        if key == "event_type" and value not in EVENT_TAXONOMY:
            raise HTTPException(status_code=422, detail="Unsupported event type")
        setattr(event, key, value)
    event.updated_at = datetime.now(timezone.utc)
    db.add(EventAudit(
        audit_id=f"AUD-{uuid.uuid4().hex[:12].upper()}", event_id=event_id, actor=actor,
        previous_value=json.dumps(previous, default=str), new_value=json.dumps(update, default=str),
        changed_at=event.updated_at,
    ))
    analyze_source_change(
        db, event.investigation_id, "RECONSTRUCTED_EVENT", event_id,
        trigger="TIMELINE_EVENT_CORRECTED", include_unlinked=False,
    )
    db.commit()
    return event_to_dict(db, event)


@app.post("/api/graph/rebuild/{investigation_id}")
def rebuild_case_graph(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    if not any(item["investigation_id"] == investigation_id for item in INVESTIGATIONS):
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        result = rebuild_graph(investigation_id, db)
        for relationship in db.scalars(select(GraphRelationship).where(
            GraphRelationship.investigation_id == investigation_id
        )).all():
            analyze_source_change(
                db, investigation_id, "GRAPH_RELATIONSHIP", relationship.relationship_id,
                trigger="GRAPH_RELATIONSHIPS_REBUILT", include_unlinked=False,
            )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Graph reconstruction failed") from exc


@app.get("/api/graph/{investigation_id}")
def get_case_graph(
    investigation_id: str,
    db: Session = Depends(get_db),
    node_type: str | None = None,
    relationship_type: str | None = None,
    verification_status: str | None = None,
    person_id: str | None = None,
    location_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    include_possible: bool = True,
) -> dict:
    return graph_payload(investigation_id, db, {
        "node_type": node_type, "relationship_type": relationship_type, "verification_status": verification_status,
        "person_id": person_id, "location_id": location_id, "start_date": start_date, "end_date": end_date,
        "include_possible": include_possible,
    })


@app.get("/api/graph/{investigation_id}/nodes/{node_id}")
def get_graph_node(investigation_id: str, node_id: str, db: Session = Depends(get_db)) -> dict:
    node = db.scalar(select(GraphNode).where(GraphNode.investigation_id == investigation_id, GraphNode.node_id == node_id))
    if not node:
        raise HTTPException(status_code=404, detail="Graph node not found")
    result = {
        "id": node.node_id, "node_type": node.node_type, "entity_id": node.entity_id,
        "display_label": node.display_label, "metadata": json.loads(node.metadata_json),
    }
    return result


@app.get("/api/graph/{investigation_id}/relationships/{relationship_id}")
def get_graph_relationship(investigation_id: str, relationship_id: str, db: Session = Depends(get_db)) -> dict:
    relationship = db.scalar(select(GraphRelationship).where(
        GraphRelationship.investigation_id == investigation_id,
        GraphRelationship.relationship_id == relationship_id,
    ))
    if not relationship:
        raise HTTPException(status_code=404, detail="Graph relationship not found")
    return relationship_detail(db, relationship_id) or {}


@app.get("/api/graph/{investigation_id}/persons/{person_id}/network")
def get_person_network(investigation_id: str, person_id: str, depth: int = 1, db: Session = Depends(get_db)) -> dict:
    return network_for_person(investigation_id, person_id, db, depth)


@app.get("/api/graph/{investigation_id}/metrics")
def get_graph_metrics(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    payload = graph_payload(investigation_id, db)
    import networkx as nx
    graph = nx.Graph()
    graph.add_nodes_from(item["id"] for item in payload["nodes"])
    graph.add_edges_from((item["source"], item["target"]) for item in payload["relationships"])
    relationships = db.scalars(select(GraphRelationship).where(GraphRelationship.investigation_id == investigation_id)).all()
    return graph_metrics_from_graph(graph, relationships)


@app.get("/api/graph/{investigation_id}/paths")
def get_graph_path(investigation_id: str, source_person: str, target_person: str, db: Session = Depends(get_db)) -> dict:
    return paths_for_people(investigation_id, source_person, target_person, db)


@app.get("/api/graph/{investigation_id}/locations/{location_id}/network")
def get_location_network(investigation_id: str, location_id: str, db: Session = Depends(get_db)) -> dict:
    payload = graph_payload(investigation_id, db, {"location_id": location_id})
    return payload


@app.patch("/api/graph/relationships/{relationship_id}/review")
def review_graph_relationship(relationship_id: str, review: RelationshipReview, db: Session = Depends(get_db)) -> dict:
    relationship = db.get(GraphRelationship, relationship_id)
    if not relationship:
        raise HTTPException(status_code=404, detail="Graph relationship not found")
    previous = relationship.verification_status
    relationship.verification_status = review.verification_status
    relationship.updated_at = datetime.now(timezone.utc)
    db.add(RelationshipReviewHistory(
        review_id=f"GRH-{uuid.uuid4().hex[:16].upper()}",
        relationship_id=relationship_id, previous_status=previous,
        new_status=review.verification_status, reviewer_note=review.reviewer_note,
        action_timestamp=relationship.updated_at,
    ))
    analyze_source_change(
        db, relationship.investigation_id, "GRAPH_RELATIONSHIP", relationship_id,
        trigger="GRAPH_RELATIONSHIP_REVIEWED", include_unlinked=False,
    )
    db.commit()
    return relationship_detail(db, relationship_id) or {}


@app.post("/api/contradictions/detect/{investigation_id}")
def detect_investigation_contradictions(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    if not any(item["investigation_id"] == investigation_id for item in INVESTIGATIONS):
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        result = detect_contradictions(investigation_id, db)
        for contradiction in db.scalars(select(Contradiction).where(
            Contradiction.investigation_id == investigation_id
        )).all():
            analyze_source_change(
                db, investigation_id, "CONTRADICTION", contradiction.contradiction_id,
                trigger="CONTRADICTION_DETECTED", include_unlinked=False,
            )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Contradiction detection failed") from exc


@app.get("/api/contradictions/{investigation_id}")
def list_contradictions(
    investigation_id: str, db: Session = Depends(get_db), contradiction_type: str | None = None,
    severity: str | None = None, status: str | None = None, person_id: str | None = None,
    page: int = 1, page_size: int = 50,
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = select(Contradiction).where(Contradiction.investigation_id == investigation_id).order_by(Contradiction.last_detected_at.desc())
    if contradiction_type: query = query.where(Contradiction.contradiction_type == contradiction_type)
    if severity: query = query.where(Contradiction.severity == severity)
    if status: query = query.where(Contradiction.status == status)
    if person_id: query = query.where(Contradiction.affected_entity_id == person_id)
    all_items = list(db.scalars(query).all())
    start = (page - 1) * page_size
    return {"items": [contradiction_dict(db, item) for item in all_items[start:start + page_size]], "total": len(all_items), "page": page, "page_size": page_size}


@app.get("/api/contradictions/{investigation_id}/statistics")
def contradiction_statistics(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    items = list(db.scalars(select(Contradiction).where(Contradiction.investigation_id == investigation_id)).all())
    return {"total": len(items), "by_severity": {value: sum(item.severity == value for item in items) for value in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")}, "by_type": {value: sum(item.contradiction_type == value for item in items) for value in sorted({item.contradiction_type for item in items})}, "by_status": {value: sum(item.status == value for item in items) for value in ("DETECTED", "UNDER_REVIEW", "CONFIRMED_CONFLICT", "RESOLVED", "DISMISSED", "REOPENED")}}


@app.get("/api/contradictions/{investigation_id}/snapshots")
def contradiction_snapshots(investigation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    items = db.scalars(select(ContradictionSnapshot).where(ContradictionSnapshot.investigation_id == investigation_id).order_by(ContradictionSnapshot.snapshot_version.desc())).all()
    return [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in items]


@app.get("/api/contradictions/{investigation_id}/{contradiction_id}")
def contradiction_detail(investigation_id: str, contradiction_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.scalar(select(Contradiction).where(Contradiction.investigation_id == investigation_id, Contradiction.contradiction_id == contradiction_id))
    if not item: raise HTTPException(status_code=404, detail="Contradiction not found")
    return contradiction_dict(db, item)


@app.get("/api/contradictions/{investigation_id}/{contradiction_id}/comparison")
def contradiction_comparison(investigation_id: str, contradiction_id: str, db: Session = Depends(get_db)) -> list[dict]:
    detail = contradiction_detail(investigation_id, contradiction_id, db)
    return detail["comparisons"]


@app.get("/api/contradictions/{investigation_id}/{contradiction_id}/evidence")
def contradiction_evidence(investigation_id: str, contradiction_id: str, db: Session = Depends(get_db)) -> list[dict]:
    detail = contradiction_detail(investigation_id, contradiction_id, db)
    return detail["evidence"]


@app.get("/api/contradictions/{investigation_id}/{contradiction_id}/network-context")
def contradiction_network_context(investigation_id: str, contradiction_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.scalar(select(Contradiction).where(Contradiction.investigation_id == investigation_id, Contradiction.contradiction_id == contradiction_id))
    if not item: raise HTTPException(status_code=404, detail="Contradiction not found")
    return {"affected_event_id": item.affected_event_id, "affected_relationship_id": item.affected_relationship_id, "person_id": item.affected_entity_id if item.affected_entity_type == "PERSON" else None}


@app.patch("/api/contradictions/{contradiction_id}/review")
def review_contradiction(contradiction_id: str, review: ContradictionReviewRequest, db: Session = Depends(get_db)) -> dict:
    item = db.get(Contradiction, contradiction_id)
    if not item: raise HTTPException(status_code=404, detail="Contradiction not found")
    if review.action in {"RESOLVED", "DISMISSED"} and not review.review_note.strip():
        raise HTTPException(status_code=422, detail="A review note is required to resolve or dismiss a contradiction")
    previous = item.status
    item.status = review.action
    item.updated_at = datetime.now(timezone.utc)
    db.add(ContradictionReview(review_id=f"CR-{uuid.uuid4().hex[:16].upper()}", contradiction_id=contradiction_id, reviewer=review.reviewer, action=review.action, review_note=review.review_note, previous_status=previous, new_status=review.action, created_at=item.updated_at))
    analyze_source_change(
        db, item.investigation_id, "CONTRADICTION", contradiction_id,
        trigger="CONTRADICTION_REVIEWED", include_unlinked=False,
    )
    db.commit()
    return contradiction_dict(db, item)


@app.post("/api/contradictions/{contradiction_id}/notes")
def add_contradiction_note(contradiction_id: str, review: ContradictionReviewRequest, db: Session = Depends(get_db)) -> dict:
    item = db.get(Contradiction, contradiction_id)
    if not item: raise HTTPException(status_code=404, detail="Contradiction not found")
    if not review.review_note.strip(): raise HTTPException(status_code=422, detail="A note is required")
    db.add(ContradictionReview(review_id=f"CR-{uuid.uuid4().hex[:16].upper()}", contradiction_id=contradiction_id, reviewer=review.reviewer, action="NOTE", review_note=review.review_note, previous_status=item.status, new_status=item.status, created_at=datetime.now(timezone.utc)))
    db.commit()
    return contradiction_dict(db, item)

# ---------------------------------------------------------------------------
# Milestone 6 · Hypothesis Intelligence Engine API
# ---------------------------------------------------------------------------


def _require_investigation(investigation_id: str) -> None:
    if not any(item["investigation_id"] == investigation_id for item in INVESTIGATIONS):
        raise HTTPException(status_code=404, detail="Investigation not found")


def _get_hypothesis(db: Session, hypothesis_id: str) -> Hypothesis:
    item = db.get(Hypothesis, hypothesis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return item


def _get_link(db: Session, link_id: str) -> HypothesisEvidenceLink:
    item = db.get(HypothesisEvidenceLink, link_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence link not found")
    return item


@app.post("/api/hypotheses/{investigation_id}", status_code=201, tags=["Hypotheses"],
          summary="Create a competing hypothesis")
def create_hypothesis(
    investigation_id: str,
    request: HypothesisCreate,
    db: Session = Depends(get_db),
) -> dict:
    """Create a hypothesis under an existing investigation. Titles must be unique
    within the investigation (case-insensitive). Unknown categories may be supplied
    as uppercase custom identifiers."""
    item = create_hypothesis_service(db, investigation_id, request.model_dump())
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@app.get("/api/hypotheses/{investigation_id}", tags=["Hypotheses"],
         summary="List hypotheses with filtering and pagination")
def list_hypotheses(
    investigation_id: str,
    db: Session = Depends(get_db),
    status: str | None = None,
    category: str | None = None,
    assessment: str | None = None,
    search: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    include_archived: bool = True,
) -> dict:
    return list_hypotheses_service(
        db, investigation_id, status=status, category=category, assessment=assessment,
        search=search, sort=sort, order=order, page=page, page_size=page_size,
        include_archived=include_archived,
    )


@app.get("/api/hypotheses/{investigation_id}/summary", tags=["Hypotheses"],
         summary="Hypothesis Lab overview statistics")
def hypothesis_summary(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    return investigation_summary(db, investigation_id)


@app.get("/api/hypotheses/{investigation_id}/sources", tags=["Hypotheses"],
         summary="Search existing investigation records available for linking")
def hypothesis_source_catalog(
    investigation_id: str,
    db: Session = Depends(get_db),
    source_type: str | None = None,
    q: str | None = None,
    hypothesis_id: str | None = None,
    limit: int = 1000,
) -> dict:
    _require_investigation(investigation_id)
    items = build_source_catalog(db, investigation_id, source_type=source_type, q=q, limit=min(max(limit, 1), 2000))
    if hypothesis_id:
        hypothesis = _get_hypothesis(db, hypothesis_id)
        if hypothesis.investigation_id != investigation_id:
            raise HTTPException(status_code=404, detail="Hypothesis not found in this investigation")
        linked = {(link["source_type"], link["source_id"]) for link in list_links(db, hypothesis)}
        for item in items:
            item["already_linked"] = (item["source_type"], item["source_id"]) in linked
    return {"investigation_id": investigation_id, "items": items, "total": len(items)}


@app.patch("/api/hypotheses/{hypothesis_id}", tags=["Hypotheses"],
           summary="Update hypothesis details")
def update_hypothesis(
    hypothesis_id: str,
    request: HypothesisUpdate,
    db: Session = Depends(get_db),
) -> dict:
    item = _get_hypothesis(db, hypothesis_id)
    update_hypothesis_service(db, item, request.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@app.patch("/api/hypotheses/{hypothesis_id}/status", tags=["Hypotheses"],
           summary="Record an investigator-controlled status decision")
def update_hypothesis_status(
    hypothesis_id: str,
    request: HypothesisStatusUpdate,
    db: Session = Depends(get_db),
) -> dict:
    item = _get_hypothesis(db, hypothesis_id)
    update_status_service(db, item, request.status, request.explanation, request.updated_by)
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@app.delete("/api/hypotheses/{hypothesis_id}", tags=["Hypotheses"],
            summary="Archive a hypothesis while retaining all history")
def archive_hypothesis(
    hypothesis_id: str,
    db: Session = Depends(get_db),
    reason: str = "",
    archived_by: str = "investigator",
) -> dict:
    item = _get_hypothesis(db, hypothesis_id)
    archive_hypothesis_service(db, item, actor=archived_by, reason=reason)
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@app.post("/api/hypotheses/{hypothesis_id}/evidence", status_code=201, tags=["Hypotheses"],
          summary="Link an existing investigation source to a hypothesis")
def link_hypothesis_evidence(
    hypothesis_id: str,
    request: HypothesisEvidenceCreate,
    db: Session = Depends(get_db),
) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    link = link_evidence(db, hypothesis, request.model_dump())
    db.commit()
    db.refresh(link)
    return link_dict(link)


@app.get("/api/hypotheses/{hypothesis_id}/evidence", tags=["Hypotheses"],
         summary="List linked sources for a hypothesis")
def list_hypothesis_evidence(
    hypothesis_id: str,
    db: Session = Depends(get_db),
    classification: str | None = None,
    review_status: str | None = None,
    source_type: str | None = None,
    include_withdrawn: bool = True,
) -> list[dict]:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    return list_links(
        db, hypothesis, classification=classification, review_status=review_status,
        source_type=source_type, include_withdrawn=include_withdrawn,
    )


@app.patch("/api/hypotheses/evidence/{link_id}", tags=["Hypotheses"],
           summary="Change classification, strength, reliability, or review status")
def update_hypothesis_evidence(
    link_id: str,
    request: HypothesisEvidenceUpdate,
    db: Session = Depends(get_db),
) -> dict:
    link = _get_link(db, link_id)
    hypothesis = _get_hypothesis(db, link.hypothesis_id)
    update_link(db, link, hypothesis, request.model_dump(exclude_none=True))
    db.commit()
    db.refresh(link)
    return link_dict(link)


@app.delete("/api/hypotheses/evidence/{link_id}", tags=["Hypotheses"],
            summary="Withdraw an evidence link while preserving its audit history")
def withdraw_hypothesis_evidence(
    link_id: str,
    db: Session = Depends(get_db),
    withdrawn_by: str = "investigator",
) -> dict:
    link = _get_link(db, link_id)
    hypothesis = _get_hypothesis(db, link.hypothesis_id)
    withdraw_link(db, link, hypothesis, actor=withdrawn_by)
    db.commit()
    db.refresh(link)
    return link_dict(link)


@app.post("/api/hypotheses/{hypothesis_id}/evaluate", tags=["Hypotheses"],
          summary="Re-evaluate one hypothesis and store an assessment snapshot")
def evaluate_one_hypothesis(hypothesis_id: str, db: Session = Depends(get_db)) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    assessment = evaluate_hypothesis_service(db, hypothesis)
    db.commit()
    return assessment_dict(assessment)


@app.post("/api/hypotheses/evaluate/{investigation_id}", tags=["Hypotheses"],
          summary="Evaluate all active hypotheses in an investigation")
def evaluate_investigation_hypotheses(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    result = evaluate_all_hypotheses(db, investigation_id)
    db.commit()
    return result


@app.get("/api/hypotheses/{hypothesis_id}/assessment", tags=["Hypotheses"],
         summary="Retrieve the latest stored assessment")
def hypothesis_assessment(hypothesis_id: str, db: Session = Depends(get_db)) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    assessment = latest_hypothesis_assessment(db, hypothesis.id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Hypothesis has not been evaluated")
    return assessment_dict(assessment)


@app.get("/api/hypotheses/{hypothesis_id}/assessments", tags=["Hypotheses"],
         summary="Retrieve the append-only assessment history")
def hypothesis_assessment_history(hypothesis_id: str, db: Session = Depends(get_db)) -> list[dict]:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    history = hypothesis_history_service(db, hypothesis)["assessments"]
    return history


@app.post("/api/hypotheses/{investigation_id}/compare", tags=["Hypotheses"],
          summary="Compare two or more competing hypotheses")
def compare_hypotheses(investigation_id: str, request: HypothesisCompareRequest, db: Session = Depends(get_db)) -> dict:
    return compare_hypotheses_service(db, investigation_id, request.hypothesis_ids)


@app.get("/api/hypotheses/{identifier}/impact", tags=["Hypotheses"],
         summary="Retrieve evidence impact records for an investigation or hypothesis")
def hypothesis_impact_records(
    identifier: str,
    db: Session = Depends(get_db),
    category: str | None = None,
    reviewed: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    if identifier.startswith("HYP-"):
        hypothesis = _get_hypothesis(db, identifier)
        return list_impacts(
            db, hypothesis_id=hypothesis.id, category=category, reviewed=reviewed,
            page=page, page_size=page_size,
        )
    _require_investigation(identifier)
    return list_impacts(
        db, investigation_id=identifier, category=category, reviewed=reviewed,
        page=page, page_size=page_size,
    )


@app.post("/api/hypotheses/{hypothesis_id}/impact/{impact_id}/review", tags=["Hypotheses"],
          summary="Record investigator review of an impact analysis item")
def review_hypothesis_impact(
    hypothesis_id: str,
    impact_id: str,
    request: ImpactReviewRequest,
    db: Session = Depends(get_db),
) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    item = review_impact(db, hypothesis, impact_id, request.reviewed_by, request.explanation)
    db.commit()
    db.refresh(item)
    return impact_dict(item)


@app.get("/api/hypotheses/{hypothesis_id}/history", tags=["Hypotheses"],
         summary="Retrieve hypothesis versions, review actions, and assessments")
def hypothesis_history(hypothesis_id: str, db: Session = Depends(get_db)) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    return hypothesis_history_service(db, hypothesis)


@app.get("/api/hypotheses/{hypothesis_id}/versions/{version_number}", tags=["Hypotheses"],
         summary="Retrieve one historical hypothesis version")
def hypothesis_version(hypothesis_id: str, version_number: int, db: Session = Depends(get_db)) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    item = version_detail(db, hypothesis.id, version_number)
    if not item:
        raise HTTPException(status_code=404, detail="Hypothesis version not found")
    return version_dict(item)


@app.post("/api/hypotheses/{hypothesis_id}/notes", status_code=201, tags=["Hypotheses"],
          summary="Add an investigator note to a hypothesis")
def add_hypothesis_note(
    hypothesis_id: str,
    request: HypothesisNoteCreate,
    db: Session = Depends(get_db),
) -> dict:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    item = add_note(db, hypothesis, request.note, request.created_by)
    db.commit()
    db.refresh(item)
    return note_dict(item)


@app.get("/api/hypotheses/{hypothesis_id}/notes", tags=["Hypotheses"],
         summary="Retrieve investigator notes")
def list_hypothesis_notes(hypothesis_id: str, db: Session = Depends(get_db)) -> list[dict]:
    hypothesis = _get_hypothesis(db, hypothesis_id)
    return list_notes(db, hypothesis)


@app.get("/api/hypotheses/{investigation_id}/{hypothesis_id}", tags=["Hypotheses"],
         summary="Retrieve hypothesis detail with evidence, assessment, and review counts")
def hypothesis_detail(investigation_id: str, hypothesis_id: str, db: Session = Depends(get_db)) -> dict:
    _require_investigation(investigation_id)
    hypothesis = _get_hypothesis(db, hypothesis_id)
    if hypothesis.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return hypothesis_detail_service(db, hypothesis)
