"""Evidence ingestion service: validation, durable storage, extraction and provenance."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from .config import settings
from .extraction import extract_bytes, normalize_records, validate_records
from .models import EvidenceRecord

ALLOWED_EXTENSIONS = {"csv", "json", "pdf", "txt"}
ALLOWED_MIME_TYPES = {
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", ""},
    "json": {"application/json", "text/json", ""},
    "pdf": {"application/pdf", ""},
    "txt": {"text/plain", ""},
}


def ingest_upload(upload: UploadFile, investigation_id: str, db: Session, category: str = "Other") -> EvidenceRecord:
    filename = Path(upload.filename or "").name
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not filename or extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only CSV, JSON, PDF, and TXT files are supported")
    if upload.content_type not in ALLOWED_MIME_TYPES[extension]:
        raise ValueError(f"Invalid content type for .{extension} file")
    payload = upload.file.read(settings.max_upload_bytes + 1)
    if len(payload) > settings.max_upload_bytes:
        raise ValueError(f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit")
    digest = hashlib.sha256(payload).hexdigest()
    if db.query(EvidenceRecord).filter(EvidenceRecord.checksum == digest).first():
        raise ValueError("This file has already been uploaded")
    record = EvidenceRecord(
        id=f"EVD-{uuid.uuid4().hex[:10].upper()}",
        filename=filename,
        investigation_id=investigation_id,
        format=extension,
        size_bytes=len(payload),
        checksum=digest,
        status="processing",
        uploaded_at=datetime.now(timezone.utc),
        provenance=json.dumps({"filename": filename, "sha256": digest, "ingested_at": datetime.now(timezone.utc).isoformat()}),
        records_json="[]",
        category=category,
    )
    storage_dir = settings.storage_dir_path
    storage_dir.mkdir(parents=True, exist_ok=True)
    relative_path = f"{record.id}.{extension}"
    (storage_dir / relative_path).write_bytes(payload)
    record.storage_path = relative_path
    record.processing_stage = "extracting"
    db.add(record)
    try:
        extracted = normalize_records(extract_bytes(filename, payload), evidence_id=record.id)
        record.processing_stage = "validating"
        errors = validate_records(extracted)
        record.records_json = json.dumps(extracted)
        record.validation_errors = json.dumps(errors)
        record.status = "validated" if not errors else "needs_review"
        record.processing_stage = "completed"
        record.record_count = len(extracted)
    except Exception as exc:
        requires_ocr = "OCR" in str(exc)
        record.status = "needs_review" if requires_ocr else "failed"
        record.processing_stage = "completed" if requires_ocr else "failed"
        record.validation_errors = json.dumps([str(exc)])
        record.record_count = 0
    db.commit()
    db.refresh(record)
    return record


def evidence_dict(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_id": record.id, "evidence_type": record.format.upper(),
        "source": record.filename, "investigation_id": record.investigation_id,
        "uploaded_at": record.uploaded_at.isoformat(), "verification_status": record.status,
        "status": record.status, "format": record.format, "size_bytes": record.size_bytes,
        "checksum": record.checksum, "record_count": record.record_count,
        "category": record.category, "processing_stage": record.processing_stage,
    }
