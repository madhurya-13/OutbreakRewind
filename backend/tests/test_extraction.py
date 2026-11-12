import json
import pytest

from app.extraction import extract_bytes, normalize_records, validate_records


def test_csv_normalization_and_validation():
    rows = extract_bytes("signals.csv", b"Case ID, Status\nC-001, confirmed\n")
    assert normalize_records(rows) == [{"case_id": "C-001", "status": "confirmed"}]
    assert validate_records(rows) == []


def test_json_records_and_text():
    payload = json.dumps({"records": [{"Signal": "alpha"}]}).encode()
    assert extract_bytes("signals.json", payload) == [{"Signal": "alpha"}]
    assert extract_bytes("notes.txt", b"synthetic note")[0]["text"] == "synthetic note"


def test_empty_records_are_invalid():
    assert validate_records([]) == ["No records were extracted"]


def test_ambiguous_dates_require_review():
    records = normalize_records([{"event_date": "2024-02-01", "case_id": "C-001"}], evidence_id="EVD-TEST")
    assert records[0]["event_date"]["requires_review"] is False
    invalid = normalize_records([{"event_date": "not-a-date", "case_id": "C-002"}], evidence_id="EVD-TEST")
    assert validate_records(invalid) == ["Record 1 has an ambiguous or invalid date"]


def test_image_only_pdf_requires_ocr():
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    document.new_page()
    with pytest.raises(ValueError, match="OCR"):
        extract_bytes("scan.pdf", document.tobytes())
