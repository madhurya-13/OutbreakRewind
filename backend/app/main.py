from datetime import date, datetime, timezone
import json
import uuid
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import Event, EventAudit, EventSource, EvidenceRecord, GraphRelationship, GraphNode, ReconstructedEvent, RelationshipReviewHistory, TemporalFinding, TemporalRelationship, TimelineSnapshot
from .evidence import evidence_dict, ingest_upload
from .schemas import EventCorrection, EventRead, HealthRead, RelationshipReview
from .intelligence.graph_service import (
    graph_metrics_from_graph, graph_payload, network_for_person, paths_for_people,
    rebuild_graph, relationship_detail,
)
from .temporal_engine import EVENT_TAXONOMY, event_to_dict, reconstruct_timeline

app = FastAPI(title="Outbreak Rewind API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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
            results.append(evidence_dict(ingest_upload(upload, investigation_id, db, category)))
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
                db.commit()
                return {"record_id": record_id, "verification_status": record["verification_status"]}
    raise HTTPException(status_code=404, detail="Extracted record not found")

@app.get("/api/dashboard/summary")
def dashboard_summary() -> dict[str, int]:
    return {"active_investigations": 8, "total_cases": 124, "evidence_records": 386, "unresolved_contradictions": 12, "active_hypotheses": 18}

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
    db.commit()
    return event_to_dict(db, event)


@app.post("/api/graph/rebuild/{investigation_id}")
def rebuild_case_graph(investigation_id: str, db: Session = Depends(get_db)) -> dict:
    if not any(item["investigation_id"] == investigation_id for item in INVESTIGATIONS):
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        return rebuild_graph(investigation_id, db)
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
    db.commit()
    return relationship_detail(db, relationship_id) or {}
