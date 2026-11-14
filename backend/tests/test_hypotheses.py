import io
import uuid

from fastapi.testclient import TestClient

from app.main import app


def _create(client, title: str) -> dict:
    response = client.post("/api/hypotheses/ORION-001", json={
        "title": title, "description": "A synthetic explanation for Project ORION.",
        "category": "SHARED_LOCATION_EXPOSURE", "assumptions": ["The location record is accurate"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_hypothesis_lifecycle_link_evaluate_compare_and_history():
    marker = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/evidence/upload",
            files={"files": (f"hypothesis-{marker}.json", io.BytesIO(b'{"records":[{"record_id":"R-' + marker.encode() + b'","location":"North"}]}'), "application/json")},
        )
        assert uploaded.status_code == 200
        evidence_id = uploaded.json()["items"][0]["evidence_id"]
        first = _create(client, f"Shared location {marker}")
        second = _create(client, f"Independent source {marker}")
        link = client.post(f"/api/hypotheses/{first['id']}/evidence", json={
            "source_type": "EVIDENCE_DOCUMENT", "source_id": evidence_id,
            "classification": "SUPPORTING", "explanation": "The original record names the shared location.",
            "evidence_strength": "MODERATE", "source_reliability": "HIGH",
        })
        assert link.status_code == 201, link.text
        duplicate = client.post(f"/api/hypotheses/{first['id']}/evidence", json={
            "source_type": "EVIDENCE_DOCUMENT", "source_id": evidence_id,
            "classification": "SUPPORTING", "explanation": "Duplicate link",
        })
        assert duplicate.status_code == 409
        link_id = link.json()["id"]
        assert client.patch(f"/api/hypotheses/evidence/{link_id}", json={"review_status": "VERIFIED"}).status_code == 200
        evaluation = client.post(f"/api/hypotheses/{first['id']}/evaluate")
        assert evaluation.status_code == 200
        assert evaluation.json()["assessment_label"] == "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE"
        comparison = client.post("/api/hypotheses/ORION-001/compare", json={"hypothesis_ids": [first["id"], second["id"]]})
        assert comparison.status_code == 200
        assert len(comparison.json()["hypotheses"]) == 2
        assert client.patch(f"/api/hypotheses/{first['id']}", json={"description": "Updated explanation", "reason": "New investigator note"}).status_code == 200
        history = client.get(f"/api/hypotheses/{first['id']}/history")
        assert history.status_code == 200
        assert len(history.json()["versions"]) >= 2
        assert client.get(f"/api/hypotheses/{first['id']}/impact").json()


def test_hypothesis_source_and_investigation_validation():
    with TestClient(app) as client:
        assert client.get("/api/hypotheses/not-an-investigation").status_code == 404
        hypothesis = _create(client, "Validation hypothesis " + uuid.uuid4().hex[:8])
        response = client.post(f"/api/hypotheses/{hypothesis['id']}/evidence", json={
            "source_type": "EVIDENCE_DOCUMENT", "source_id": "missing",
            "classification": "NEUTRAL", "explanation": "There is no source.",
        })
        assert response.status_code == 404
        comparison = client.post("/api/hypotheses/ORION-001/compare", json={"hypothesis_ids": [hypothesis["id"], "missing"]})
        assert comparison.status_code == 404
