import io
import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_graph_rebuild_extracts_contact_location_edges_and_is_idempotent():
    marker = uuid.uuid4().hex[:8]
    person_a, person_b = f"P-A-{marker}", f"P-B-{marker}"
    payload = (
        '{"records": ['
        f'{{"record_id":"R-A-{marker}","person_id":"{person_a}","contact_person_id":"{person_b}","shared_event_id":"GATHERING-{marker}","contact_date":"2024-06-10","visit_date":"2024-06-10","location_id":"LOC-GRAPH-{marker}","description":"documented contact"}},'
        f'{{"record_id":"R-B-{marker}","person_id":"{person_b}","shared_event_id":"GATHERING-{marker}","visit_date":"2024-06-10","location_id":"LOC-GRAPH-{marker}","description":"shared visit"}}'
        ']}'
    ).encode()
    with TestClient(app) as client:
        assert client.post("/api/evidence/upload", files={"files": ("graph.json", io.BytesIO(payload), "application/json")}).status_code == 200
        assert client.post("/api/timeline/reconstruct/ORION-001").status_code == 200
        first = client.post("/api/graph/rebuild/ORION-001")
        assert first.status_code == 200
        body = first.json()
        assert body["node_count"] >= 5
        assert body["relationship_count"] >= 2
        graph = client.get("/api/graph/ORION-001", params={"include_possible": True}).json()
        types = {edge["relationship_type"] for edge in graph["relationships"]}
        assert "DIRECT_CONTACT" in types
        assert "SAME_LOCATION_OVERLAPPING_TIME" in types
        assert "SHARED_EVENT" in types
        second = client.post("/api/graph/rebuild/ORION-001").json()
        assert second["node_count"] == body["node_count"]
        assert second["relationship_count"] == body["relationship_count"]
        direct = next(edge for edge in graph["relationships"] if edge["relationship_type"] == "DIRECT_CONTACT")
        assert direct["sources"]
        reviewed = client.patch(f"/api/graph/relationships/{direct['id']}/review", json={"verification_status": "REJECTED", "reviewer_note": "Needs review"})
        assert reviewed.status_code == 200
        assert reviewed.json()["verification_status"] == "REJECTED"
        assert client.get("/api/graph/ORION-001/metrics").status_code == 200
        assert client.get("/api/graph/ORION-001/persons/" + person_a + "/network").status_code == 200
        path = client.get("/api/graph/ORION-001/paths", params={"source_person": person_a, "target_person": person_b}).json()
        assert path["path"]
