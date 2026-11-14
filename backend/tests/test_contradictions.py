import io
import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_detection_finds_date_location_lab_and_missing_conflicts_and_is_idempotent():
    marker = uuid.uuid4().hex[:8]
    payload = (
        '{"records": ['
        f'{{"record_id":"A-{marker}","person_id":"P-{marker}","event_date":"2024-06-10","location_id":"LOC-A","sample_id":"S-{marker}","laboratory_result":"positive"}},'
        f'{{"record_id":"B-{marker}","person_id":"P-{marker}","event_date":"2024-06-12","location_id":"LOC-B","sample_id":"S-{marker}","laboratory_result":"negative"}},'
        f'{{"record_id":"C-{marker}","person_id":"Q-{marker}","sample_id":"S-{marker}"}}'
        ']}'
    ).encode()
    with TestClient(app) as client:
        assert client.post("/api/evidence/upload", files={"files": ("conflicts.json", io.BytesIO(payload), "application/json")}).status_code == 200
        assert client.post("/api/timeline/reconstruct/ORION-001").status_code == 200
        first = client.post("/api/contradictions/detect/ORION-001")
        assert first.status_code == 200
        findings = client.get("/api/contradictions/ORION-001", params={"page_size": 100}).json()["items"]
        kinds = {item["contradiction_type"] for item in findings}
        assert {"DATE_CONFLICT", "LOCATION_CONFLICT", "LAB_RESULT_CONFLICT"} <= kinds
        assert client.get("/api/contradictions/ORION-001", params={"contradiction_type": "SAMPLE_OWNER_CONFLICT", "page_size": 100}).json()["items"]
        item = next(item for item in findings if item["contradiction_type"] == "DATE_CONFLICT")
        detail = client.get(f"/api/contradictions/ORION-001/{item['contradiction_id']}").json()
        assert detail["comparisons"] and detail["evidence"]
        assert client.patch(f"/api/contradictions/{item['contradiction_id']}/review", json={"action": "RESOLVED"}).status_code == 422
        reviewed = client.patch(f"/api/contradictions/{item['contradiction_id']}/review", json={"action": "RESOLVED", "review_note": "Reviewed source documents"})
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "RESOLVED"
        second = client.post("/api/contradictions/detect/ORION-001").json()
        assert second["detected_count"] == first.json()["detected_count"]
        assert client.get("/api/contradictions/ORION-001/statistics").status_code == 200
        assert client.get("/api/contradictions/ORION-001/snapshots").json()
