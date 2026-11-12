from datetime import date
import json
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import Event, EvidenceRecord
from .evidence import evidence_dict, ingest_upload
from .schemas import EventRead, HealthRead

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
