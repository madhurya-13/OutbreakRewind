import io
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.temporal_engine import classify_event, interpret_date


def test_date_interpretation_preserves_uncertainty():
    assert interpret_date("2024-06-10").precision == "DAY"
    assert interpret_date("06/10/2024").status == "REQUIRES_REVIEW"
    assert interpret_date("June 2024").precision == "MONTH"
    assert interpret_date("early June 2024").precision == "APPROXIMATE"
    assert interpret_date("not a date").precision == "UNKNOWN"


def test_event_classifier_has_unknown_fallback():
    assert classify_event({"symptom_start_date": "2024-06-10"})[0] == "SYMPTOM_ONSET"
    assert classify_event({"description": "unrelated note"})[0] == "UNKNOWN_EVENT"


def test_reconstruct_timeline_and_sources():
    marker = uuid.uuid4().hex[:8]
    payload = (
        '{"records": ['
        f'{{"person_id": "P-{marker}", "symptom_start_date": "2024-06-10", "description": "Symptoms"}},'
        f'{{"person_id": "P-{marker}", "exposure_date": "06/11/2024", "description": "Exposure"}}'
        ']}'
    ).encode()
    with TestClient(app) as client:
        upload = client.post("/api/evidence/upload", files={"files": ("temporal.json", io.BytesIO(payload), "application/json")})
        assert upload.status_code == 200
        reconstruction = client.post("/api/timeline/reconstruct/ORION-001")
        assert reconstruction.status_code == 200
        timeline = client.get("/api/timeline/ORION-001", params={"person_id": f"P-{marker}"}).json()
        assert {event["event_type"] for event in timeline} == {"SYMPTOM_ONSET", "SUSPECTED_EXPOSURE"}
        assert all(event["sources"] for event in timeline)
        assert client.get("/api/timeline/ORION-001/statistics").status_code == 200
        assert client.get("/api/timeline/ORION-001/snapshots").json()


def test_event_correction_is_validated_and_audited():
    marker = uuid.uuid4().hex[:8]
    payload = f'{{"records":[{{"person_id":"P-{marker}","symptom_start_date":"2024-06-10"}}]}}'.encode()
    with TestClient(app) as client:
        assert client.post("/api/evidence/upload", files={"files": ("correction.json", io.BytesIO(payload), "application/json")}).status_code == 200
        client.post("/api/timeline/reconstruct/ORION-001")
        event = client.get("/api/timeline/ORION-001", params={"person_id": f"P-{marker}"}).json()[0]
        corrected = client.patch(f"/api/timeline/events/{event['event_id']}", json={"actor": "reviewer", "event_description": "Reviewed onset"})
        assert corrected.status_code == 200
        assert client.patch(f"/api/timeline/events/{event['event_id']}", json={"event_type": "NOT_A_TYPE"}).status_code == 422


def test_orion_fixture_meets_temporal_acceptance_shape():
    fixture = json.loads(Path("synthetic_data/temporal_orion.json").read_text(encoding="utf-8"))
    records = fixture["records"]
    assert len({record["person_id"] for record in records}) == 10
    assert len({record["location_id"] for record in records}) == 4
    assert sum("contact_date" in record for record in records) + sum("contact_date_2" in record for record in records) >= 15
    assert sum("collection_date" in record for record in records) >= 10
    assert sum("symptom_start_date" in record for record in records) >= 10
    assert sum("visit_date" in record for record in records) >= 5
