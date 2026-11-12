import io
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


def test_upload_and_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    payload = f"case,status\nC-{uuid.uuid4().hex[:8]},confirmed\n".encode()
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence/upload",
            files={"files": ("synthetic.csv", io.BytesIO(payload), "text/csv")},
        )
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["status"] == "validated"
        detail = client.get(f"/api/evidence/{item['evidence_id']}")
        assert detail.status_code == 200
        records = client.get(f"/api/evidence/{item['evidence_id']}/records").json()["records"]
        assert records[0]["case"].startswith("C-")
        assert client.get(f"/api/evidence/{item['evidence_id']}/source").status_code == 200
        verification = client.patch(f"/api/evidence/records/{records[0]['record_id']}/verify")
        assert verification.json()["verification_status"] == "VERIFIED"
    with TestClient(app) as restarted_client:
        assert restarted_client.get(f"/api/evidence/{item['evidence_id']}").status_code == 200
