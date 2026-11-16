import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app


def _upload(client, marker: str, person: str = "P-RW") -> dict:
    payload = (
        '{"records":[{"person_id":"' + person + marker + '","symptom_start_date":"2024-06-10",'
        '"description":"Rewind historical record"}]}'
    ).encode()
    response = client.post("/api/evidence/upload", files={"files": (f"rewind-{marker}.json", io.BytesIO(payload), "application/json")})
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def test_rewind_excludes_future_evidence_and_records_history():
    marker = uuid.uuid4().hex[:8]
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    with TestClient(app) as client:
        item = _upload(client, marker)
        after = datetime.now(timezone.utc) + timedelta(seconds=1)
        history = client.get("/api/rewind/ORION-001/history", params={"event_type": "EVIDENCE_UPLOADED"}).json()
        assert any(row["entity_id"] == item["evidence_id"] for row in history["items"])
        early = client.get("/api/rewind/ORION-001/at", params={"as_of": _iso(before)}).json()
        late = client.get("/api/rewind/ORION-001/at", params={"as_of": _iso(after)}).json()
        assert item["evidence_id"] not in {row["evidence_id"] for row in early["evidence"]}
        assert item["evidence_id"] in {row["evidence_id"] for row in late["evidence"]}
        assert late["coverage"]["status"] in {"PARTIAL", "COMPLETE"}
        assert client.get("/api/rewind/ORION-001/at", params={"as_of": "not-a-timestamp"}).status_code == 422
        assert client.get("/api/rewind/not-an-investigation/at", params={"as_of": _iso(after)}).status_code == 404


def test_rewind_snapshot_is_immutable_and_integrity_checked():
    marker = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        item = _upload(client, marker)
        cutoff = _iso(datetime.now(timezone.utc) + timedelta(seconds=1))
        created = client.post("/api/rewind/ORION-001/snapshots", json={"name": f"Snapshot {marker}", "event_cutoff": cutoff})
        assert created.status_code == 201, created.text
        snapshot = created.json()
        original_hash = snapshot["integrity_hash"]
        original_data = snapshot["snapshot_data"]
        _upload(client, marker + "B")
        fetched = client.get(f"/api/rewind/ORION-001/snapshots/{snapshot['snapshot_id']}").json()
        assert fetched["integrity_hash"] == original_hash
        assert fetched["snapshot_data"] == original_data
        integrity = client.get(f"/api/rewind/ORION-001/snapshots/{snapshot['snapshot_id']}/integrity").json()
        assert integrity["valid"] is True
        assert item["evidence_id"] in {row["evidence_id"] for row in fetched["snapshot_data"]["evidence"]}


def test_rewind_comparison_and_reports():
    marker = uuid.uuid4().hex[:8]
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    with TestClient(app) as client:
        item = _upload(client, marker)
        after = datetime.now(timezone.utc) + timedelta(seconds=1)
        comparison = client.post("/api/rewind/ORION-001/compare", json={"timestamp_a": _iso(before), "timestamp_b": _iso(after), "save": True})
        assert comparison.status_code == 200, comparison.text
        payload = comparison.json()
        assert any(row["entity_id"] == item["evidence_id"] and row["difference_type"] == "ADDED" for row in payload["differences"])
        assert payload["summary"]
        assert client.get("/api/rewind/ORION-001/comparisons").json()
        for export_type in ("CSV", "PDF"):
            response = client.post("/api/rewind/ORION-001/export", json={"export_type": export_type, "cutoff_timestamp": _iso(after)})
            assert response.status_code == 201, response.text
            download = client.get(response.json()["download_url"])
            assert download.status_code == 200
            assert download.content
            if export_type == "PDF":
                assert download.content.startswith(b"%PDF")
            else:
                assert item["evidence_id"].encode() in download.content or b"investigation_id" in download.content


def test_rewind_hypothesis_evolution_and_validation():
    marker = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        evidence = _upload(client, marker)
        hypothesis = client.post("/api/hypotheses/ORION-001", json={
            "title": f"Rewind evolution {marker}", "description": "A synthetic explanation for rewind testing.",
            "category": "SHARED_LOCATION_EXPOSURE",
        })
        assert hypothesis.status_code == 201, hypothesis.text
        hypothesis_id = hypothesis.json()["id"]
        link = client.post(f"/api/hypotheses/{hypothesis_id}/evidence", json={
            "source_type": "EVIDENCE_DOCUMENT", "source_id": evidence["evidence_id"],
            "classification": "SUPPORTING", "explanation": "The uploaded record is relevant to the explanation.",
            "review_status": "VERIFIED",
        })
        assert link.status_code == 201, link.text
        evaluation = client.post(f"/api/hypotheses/{hypothesis_id}/evaluate")
        assert evaluation.status_code == 200
        evolution = client.get(f"/api/rewind/ORION-001/hypotheses/{hypothesis_id}/evolution")
        assert evolution.status_code == 200, evolution.text
        assert evolution.json()["assessments"]
        assert evolution.json()["changes"]
        validation = client.post("/api/rewind/ORION-001/validate")
        assert validation.status_code == 200
        assert validation.json()["valid"] is True