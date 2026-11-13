"""Deterministic document extraction, field normalization, and validation."""
import csv
import json
import io
import warnings
from collections.abc import Iterable
from datetime import datetime
from typing import Any

ALIASES = {
    "person_id": {"person_id", "patient_id", "individual_id", "subject_id"},
    "event_date": {"event_date", "date", "occurrence_date", "report_date", "onset_date"},
    "location": {"location", "place", "address", "site", "facility"},
    "laboratory_result": {"laboratory_result", "test_result", "lab_result", "result"},
    "contact_person_id": {"contact_person_id", "contact_person", "contact_id"},
}


def extract_bytes(filename: str, payload: bytes) -> list[dict[str, Any]]:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "csv":
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        records = []
        for index, row in enumerate(reader, 2):
            if None in row:
                warnings.warn(f"Skipping extra CSV fields on row {index}", RuntimeWarning, stacklevel=2)
                row.pop(None, None)
            records.append({**row, "_source_row": index})
        return records
    if extension == "json":
        value = json.loads(payload.decode("utf-8-sig"))
        if isinstance(value, dict):
            value = value.get("records", value.get("data", [value]))
        if not isinstance(value, list):
            raise ValueError("JSON must contain an object or array of records")
        return [item if isinstance(item, dict) else {"value": item} for item in value]
    if extension == "txt":
        text = payload.decode("utf-8-sig")
        if not text.strip():
            return []
        return [{"text": text, "_extraction_method": "utf8"}]
    if extension == "pdf":
        import fitz
        document = fitz.open(stream=payload, filetype="pdf")
        records = []
        for page in document:
            text = page.get_text("text").strip()
            method = "pymupdf"
            if not text:
                try:
                    import pytesseract
                    from PIL import Image
                except ImportError as exc:
                    raise ValueError("OCR is required but the OCR runtime is unavailable") from exc
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                try:
                    text = pytesseract.image_to_string(
                        Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                    ).strip()
                except pytesseract.TesseractNotFoundError as exc:
                    raise ValueError("OCR is required but the Tesseract executable is unavailable") from exc
                method = "tesseract"
            records.append({"page": page.number + 1, "text": text, "_extraction_method": method})
        if not any(record["text"] for record in records):
            raise ValueError("PDF contains no selectable text; OCR returned no text")
        return records
    raise ValueError("Unsupported file format")


def _date_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {"original": value, "normalized": None, "requires_review": value is not None}
    text = value.strip()
    parsed = []
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed.append(datetime.strptime(text[:19], fmt).date().isoformat())
        except ValueError:
            continue
    if len(set(parsed)) == 1:
        return {"original": value, "normalized": parsed[0], "requires_review": False}
    return {"original": value, "normalized": None, "requires_review": True}


def normalize_records(records: Iterable[dict[str, Any]], evidence_id: str | None = None) -> list[dict[str, Any]]:
    normalized = []
    for index, record in enumerate(records, 1):
        fields: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}
        for key, value in record.items():
            original_name = str(key).strip()
            if not original_name or original_name.startswith("_"):
                continue
            clean_name = original_name.lower().replace(" ", "_")
            target = next((name for name, aliases in ALIASES.items() if clean_name in aliases), clean_name)
            value = value.strip() if isinstance(value, str) else value
            if target == "event_date":
                fields[target] = _date_value(value)
            elif clean_name in set().union(*ALIASES.values()) or target in ALIASES:
                fields[target] = value
            else:
                fields[clean_name] = value
                unmapped[original_name] = value
        if evidence_id is not None:
            fields.update({
                "record_id": f"{evidence_id}_{index:03d}",
                "original_data": record,
                "unmapped_fields": unmapped,
                "source_evidence_id": evidence_id,
                "source_page": record.get("page"),
                "source_row": record.get("_source_row"),
                "extraction_method": record.get("_extraction_method", "structured_parser"),
                "verification_status": "PENDING",
            })
        normalized.append(fields)
    return normalized


def validate_records(records: list[dict[str, Any]]) -> list[str]:
    errors = []
    if not records:
        return ["No records were extracted"]
    seen = set()
    for index, record in enumerate(records, 1):
        if not record:
            errors.append(f"Record {index} is empty")
        signature = json.dumps(record.get("original_data", record), sort_keys=True, default=str)
        if signature in seen:
            errors.append(f"Record {index} duplicates an earlier record")
        seen.add(signature)
        if record.get("event_date", {}).get("requires_review"):
            errors.append(f"Record {index} has an ambiguous or invalid date")
        original_data = record.get("original_data", {})
        source = original_data or record
        has_content = any(
            value not in (None, "")
            for key, value in source.items()
            if not (isinstance(key, str) and key.startswith("_"))
        )
        if not has_content:
            errors.append(f"Record {index} has no usable data")
    return errors
