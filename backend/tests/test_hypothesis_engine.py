"""Milestone 6 integration tests using the real FastAPI app and database.

Each test creates uniquely named synthetic source records so the shared local
database remains usable across runs. No production or real patient data is used.
"""
import io
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import EvidenceRecord


def marker() -> str:
    return uuid.uuid4().hex[:8]


def create_hypothesis(client: TestClient, title: str, investigation: str = "ORION-001", **extra) -> dict:
    payload = {
        "title": title,
        "category": "SHARED_LOCATION_EXPOSURE",
        "description": "A synthetic competing explanation for Project ORION integration testing.",
        "detailed_explanation": "The explanation predicts a shared exposure followed by the observed case reports.",
        "assumptions": ["The reported location is accurate."],
        "predictions": ["Cases should share a location record."],
        "limitations": ["Records are interview-based."],
        "open_questions": ["Is the location verified?"],
        "created_by": "pytest",
        **extra,
    }
    response = client.post(f"/api/hypotheses/{investigation}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def upload_fixture(client: TestClient) -> dict:
    """Create timeline, graph, contradiction, and temporal sources for one test."""
    tag = marker()
    payload = (
        '{"records": ['
        f'{{"record_id":"A-{tag}","person_id":"P-A-{tag}","contact_person_id":"P-B-{tag}","event_date":"2024-06-10","contact_date":"2024-06-10","visit_date":"2024-06-10","location_id":"LOC-X-{tag}","sample_id":"S-{tag}","laboratory_result":"positive","description":"Synthetic shared location record {tag}"}},'
        f'{{"record_id":"B-{tag}","person_id":"P-B-{tag}","event_date":"2024-06-12","visit_date":"2024-06-12","location_id":"LOC-Y-{tag}","sample_id":"S-{tag}","laboratory_result":"negative","description":"Synthetic conflicting record {tag}"}},'
        f'{{"record_id":"C-{tag}","person_id":"P-C-{tag}","sample_id":"S-{tag}","description":"Synthetic ownership conflict {tag}"}},'
        f'{{"record_id":"D-{tag}","person_id":"P-D-{tag}","collection_date":"2024-06-20","confirmation_date":"2024-06-19","event_date":"2024-06-20","location_id":"LOC-X-{tag}","description":"Synthetic temporal ordering conflict {tag}"}}'
        ']}'
    ).encode()
    upload = client.post("/api/evidence/upload", files={
        "files": (f"hypothesis-engine-{tag}.json", io.BytesIO(payload), "application/json"),
    })
    assert upload.status_code == 200, upload.text
    evidence_id = upload.json()["items"][0]["evidence_id"]
    assert client.post("/api/timeline/reconstruct/ORION-001").status_code == 200
    assert client.post("/api/graph/rebuild/ORION-001").status_code == 200
    assert client.post("/api/contradictions/detect/ORION-001").status_code == 200

    records = client.get(f"/api/evidence/{evidence_id}/records").json()["records"]
    timeline = client.get("/api/timeline/ORION-001", params={"person_id": f"P-A-{tag}"}).json()
    graph = client.get("/api/graph/ORION-001", params={"include_possible": True}).json()
    node_labels = {node["id"]: node["display_label"] for node in graph["nodes"]}
    direct = next((edge for edge in graph["relationships"]
                   if edge["relationship_type"] == "DIRECT_CONTACT"
                   and f"P-A-{tag}" in f"{node_labels.get(edge['source'], '')} {node_labels.get(edge['target'], '')}"
                   and f"P-B-{tag}" in f"{node_labels.get(edge['source'], '')} {node_labels.get(edge['target'], '')}"), None)
    contradictions = client.get("/api/contradictions/ORION-001", params={
        "person_id": f"P-A-{tag}", "page_size": 100,
    }).json()["items"]
    if not contradictions:
        contradictions = client.get("/api/contradictions/ORION-001", params={"page_size": 100}).json()["items"]
    findings = client.get("/api/timeline/ORION-001/findings").json()
    return {
        "tag": tag, "evidence_id": evidence_id, "records": records,
        "event": timeline[0], "graph": direct,
        "contradiction": contradictions[0] if contradictions else None,
        "finding": findings[0] if findings else None,
    }


def link(client: TestClient, hypothesis_id: str, source_type: str, source_id: str,
         classification: str = "SUPPORTING", **extra) -> dict:
    payload = {
        "source_type": source_type,
        "source_id": source_id,
        "classification": classification,
        "explanation": "Linked by an integration test with an explicit reason for the classification.",
        "evidence_strength": "MODERATE",
        "source_reliability": "MODERATE",
        "linked_by": "pytest",
        **extra,
    }
    response = client.post(f"/api/hypotheses/{hypothesis_id}/evidence", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_lifecycle_listing_validation_and_archive():
    tag = marker()
    with TestClient(app) as client:
        item = create_hypothesis(client, f"Lifecycle {tag}", initial_notes="Initial synthetic note.")
        assert item["status"] == "DRAFT"
        assert item["current_assessment"] == "NOT_YET_EVALUATED"
        assert item["current_version"] == 1

        duplicate = client.post("/api/hypotheses/ORION-001", json={
            "title": f"Lifecycle {tag}", "description": "Duplicate title must be rejected.",
        })
        assert duplicate.status_code == 409

        listing = client.get("/api/hypotheses/ORION-001", params={"search": tag}).json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == item["id"]

        missing = client.get(f"/api/hypotheses/ORION-001/{item['id']}")
        assert missing.status_code == 200
        assert missing.json()["notes_count"] == 1

        updated = client.patch(f"/api/hypotheses/{item['id']}", json={
            "title": f"Lifecycle updated {tag}",
            "description": "Updated synthetic description with enough detail.",
            "assumptions": ["Updated assumption"],
            "reason": "Investigator refined the explanation.",
            "updated_by": "pytest",
        })
        assert updated.status_code == 200
        assert updated.json()["current_version"] > item["current_version"]

        status = client.patch(f"/api/hypotheses/{item['id']}/status", json={
            "status": "UNDER_INVESTIGATION", "explanation": "Now under review.",
        })
        assert status.status_code == 200
        assert status.json()["status"] == "UNDER_INVESTIGATION"

        note = client.post(f"/api/hypotheses/{item['id']}/notes", json={"note": "A second synthetic note."})
        assert note.status_code == 201
        assert len(client.get(f"/api/hypotheses/{item['id']}/notes").json()) == 2

        archived = client.delete(f"/api/hypotheses/{item['id']}", params={"reason": "Superseded by a refined explanation."})
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"
        assert archived.json()["archived_at"]
        assert client.get(f"/api/hypotheses/ORION-001/{item['id']}").status_code == 200

        history = client.get(f"/api/hypotheses/{item['id']}/history").json()
        assert len(history["versions"]) >= 4
        assert history["reviews"]
        assert any(action["action"] == "ARCHIVED" for action in history["reviews"])
        version = client.get(f"/api/hypotheses/{item['id']}/versions/{history['versions'][0]['version_number']}")
        assert version.status_code == 200
        assert version.json()["snapshot_data"]["status"] == "ARCHIVED"

        assert client.get("/api/hypotheses/UNKNOWN").status_code == 404
        assert client.get(f"/api/hypotheses/ORION-001/{item['id']}").status_code == 200
        assert client.get("/api/hypotheses/ORION-002/" + item["id"]).status_code == 404


def test_links_all_source_types_classifications_and_withdrawal_history():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        hypothesis = create_hypothesis(client, f"All sources {fixture['tag']}")
        document_link = link(client, hypothesis["id"], "EVIDENCE_DOCUMENT", fixture["evidence_id"], "CONTEXTUAL")
        record_link = link(client, hypothesis["id"], "EXTRACTED_RECORD", fixture["records"][0]["record_id"], "SUPPORTING")
        event_link = link(client, hypothesis["id"], "RECONSTRUCTED_EVENT", fixture["event"]["event_id"], "NEUTRAL")
        assert fixture["graph"], "fixture must create an explicit graph relationship"
        graph_link = link(client, hypothesis["id"], "GRAPH_RELATIONSHIP", fixture["graph"]["id"], "SUPPORTING")
        assert fixture["contradiction"], "fixture must create a contradiction"
        contradiction_link = link(client, hypothesis["id"], "CONTRADICTION", fixture["contradiction"]["contradiction_id"], "CONTRADICTING")
        if fixture["finding"]:
            link(client, hypothesis["id"], "TEMPORAL_FINDING", fixture["finding"]["finding_id"], "NEUTRAL")

        links = client.get(f"/api/hypotheses/{hypothesis['id']}/evidence").json()
        assert {item["source_type"] for item in links} >= {
            "EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT", "GRAPH_RELATIONSHIP", "CONTRADICTION",
        }
        assert {item["classification"] for item in links} >= {"SUPPORTING", "CONTRADICTING", "NEUTRAL", "CONTEXTUAL"}
        assert all(item["source_snapshot"]["title"] for item in links)
        assert all(item["explanation"] for item in links)

        duplicate = client.post(f"/api/hypotheses/{hypothesis['id']}/evidence", json={
            "source_type": "EXTRACTED_RECORD", "source_id": fixture["records"][0]["record_id"],
            "classification": "SUPPORTING", "explanation": "Duplicate attempt.",
        })
        assert duplicate.status_code == 409
        assert "already linked" in duplicate.json()["detail"]

        invalid = client.post(f"/api/hypotheses/{hypothesis['id']}/evidence", json={
            "source_type": "RECONSTRUCTED_EVENT", "source_id": "EVT-DOES-NOT-EXIST",
            "classification": "SUPPORTING", "explanation": "This source does not exist.",
        })
        assert invalid.status_code == 404

        invalid_type = client.post(f"/api/hypotheses/{hypothesis['id']}/evidence", json={
            "source_type": "INTERNET_RUMOUR", "source_id": "x",
            "classification": "SUPPORTING", "explanation": "Unsupported source type.",
        })
        assert invalid_type.status_code == 422

        changed = client.patch(f"/api/hypotheses/evidence/{record_link['link_id']}", json={
            "classification": "CONTRADICTING",
            "evidence_strength": "STRONG",
            "source_reliability": "HIGH",
            "review_status": "VERIFIED",
            "strength_reason": "The record directly contradicts a stated assumption and is verified.",
            "reliability_reason": "The original record was manually verified.",
            "investigator_notes": "Classification changed after reviewing the source.",
            "updated_by": "pytest",
        })
        assert changed.status_code == 200
        body = changed.json()
        assert body["classification"] == "CONTRADICTING"
        assert body["evidence_strength"] == "STRONG"
        assert body["source_reliability"] == "HIGH"
        assert body["review_status"] == "VERIFIED"
        assert body["reviewed_by"] == "pytest"
        assert body["strength_reason"].startswith("The record directly")

        withdrawn = client.delete(f"/api/hypotheses/evidence/{graph_link['link_id']}")
        assert withdrawn.status_code == 200
        assert withdrawn.json()["review_status"] == "WITHDRAWN"
        assert client.get(f"/api/hypotheses/{hypothesis['id']}/evidence").json()
        relink = client.post(f"/api/hypotheses/{hypothesis['id']}/evidence", json={
            "source_type": "GRAPH_RELATIONSHIP", "source_id": fixture["graph"]["id"],
            "classification": "SUPPORTING", "explanation": "Attempt to relink a withdrawn source.",
        })
        assert relink.status_code == 409
        assert "withdrawn" in relink.json()["detail"]

        history = client.get(f"/api/hypotheses/{hypothesis['id']}/history").json()
        assert any(action["action"] == "EVIDENCE_LINK_WITHDRAWN" for action in history["reviews"])
        assert any(action["action"] == "EVIDENCE_LINK_UPDATED" for action in history["reviews"])
        # A source may intentionally be linked to multiple competing hypotheses.
        other = create_hypothesis(client, f"Competing source {fixture['tag']}")
        link(client, other["id"], "EXTRACTED_RECORD", fixture["records"][0]["record_id"], "CONTEXTUAL")
        assert client.get(f"/api/hypotheses/{other['id']}/evidence").status_code == 200
        assert document_link and event_link and contradiction_link


def test_evaluation_rules_missing_information_and_reproducibility():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        hypothesis = create_hypothesis(client, f"Evaluation {fixture['tag']}")

        empty = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate")
        assert empty.status_code == 200
        assert empty.json()["assessment_label"] == "NOT_YET_EVALUATED"

        pending = link(client, hypothesis["id"], "EXTRACTED_RECORD", fixture["records"][0]["record_id"], "SUPPORTING")
        first = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert first["assessment_label"] == "INSUFFICIENT_INFORMATION"
        assert first["pending_review_count"] == 1
        assert first["assessment_details"]["explanation"]["recommended_next_review"]
        assert first["assessment_details"]["explanation"]["rule_version"] == "6.2"

        client.patch(f"/api/hypotheses/evidence/{pending['link_id']}", json={
            "review_status": "REVIEWED", "evidence_strength": "MODERATE",
        })
        partial = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert partial["assessment_label"] == "PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE"

        client.patch(f"/api/hypotheses/evidence/{pending['link_id']}", json={
            "review_status": "VERIFIED", "evidence_strength": "STRONG",
        })
        substantial = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert substantial["assessment_label"] == "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE"
        assert substantial["strong_count"] == 1
        assert substantial["verified_count"] == 1

        contradiction = link(client, hypothesis["id"], "CONTRADICTION", fixture["contradiction"]["contradiction_id"], "CONTRADICTING")
        client.patch(f"/api/hypotheses/evidence/{contradiction['link_id']}", json={"review_status": "VERIFIED"})
        mixed = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert mixed["assessment_label"] in {"MIXED_EVIDENCE", "SIGNIFICANT_CONTRADICTIONS"}
        assert mixed["assessment_details"]["explanation"]["conflicting_sources"]
        assert mixed["assessment_details"]["explanation"]["why"]

        # A second unresolved linked contradiction must produce the documented
        # significant-contradiction label.
        other_contradiction = next(
            item for item in client.get("/api/contradictions/ORION-001", params={"page_size": 200}).json()["items"]
            if item["contradiction_id"] != fixture["contradiction"]["contradiction_id"]
        )
        second = link(client, hypothesis["id"], "CONTRADICTION", other_contradiction["contradiction_id"], "CONTRADICTING")
        client.patch(f"/api/hypotheses/evidence/{second['link_id']}", json={"review_status": "VERIFIED"})
        significant = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert significant["assessment_label"] == "SIGNIFICANT_CONTRADICTIONS"
        assert significant["unresolved_contradiction_count"] >= 2

        repeat = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert repeat["assessment_label"] == significant["assessment_label"]
        assert repeat["supporting_count"] == significant["supporting_count"]
        assert repeat["contradicting_count"] == significant["contradicting_count"]
        assert repeat["evaluation_rule_version"] == significant["evaluation_rule_version"]

        assessments = client.get(f"/api/hypotheses/{hypothesis['id']}/assessments").json()
        assert len(assessments) >= 6
        labels = {item["assessment_label"] for item in assessments}
        assert "INSUFFICIENT_INFORMATION" in labels
        assert "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE" in labels

        latest = client.get(f"/api/hypotheses/{hypothesis['id']}/assessment").json()
        assert latest["assessment_label"] == "SIGNIFICANT_CONTRADICTIONS"


def test_missing_source_is_reported_without_deleting_the_link():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        hypothesis = create_hypothesis(client, f"Missing source {fixture['tag']}")
        link(client, hypothesis["id"], "EVIDENCE_DOCUMENT", fixture["evidence_id"], "SUPPORTING")
        with SessionLocal() as db:
            record = db.get(EvidenceRecord, fixture["evidence_id"])
            assert record
            db.delete(record)
            db.commit()
        assessment = client.post(f"/api/hypotheses/{hypothesis['id']}/evaluate").json()
        assert assessment["assessment_details"]["counts"]["missing_sources"] == 1
        assert assessment["assessment_details"]["missing_information_severity"] == "HIGH"
        assert any("can no longer be found" in item for item in assessment["missing_information"])
        links = client.get(f"/api/hypotheses/{hypothesis['id']}/evidence").json()
        assert links and links[0]["source_title"]


def test_comparison_matrix_shared_sources_and_investigation_boundary():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        first = create_hypothesis(client, f"Compare A {fixture['tag']}")
        second = create_hypothesis(client, f"Compare B {fixture['tag']}", category="PERSON_TO_PERSON_CONTACT")
        third = create_hypothesis(client, f"Compare C {fixture['tag']}", category="REPORTING_OR_DATA_ERROR")
        first_link = link(client, first["id"], "EXTRACTED_RECORD", fixture["records"][0]["record_id"], "SUPPORTING")
        client.patch(f"/api/hypotheses/evidence/{first_link['link_id']}", json={"review_status": "VERIFIED"})
        link(client, second["id"], "EXTRACTED_RECORD", fixture["records"][0]["record_id"], "CONTRADICTING")
        client.post(f"/api/hypotheses/{first['id']}/evaluate")

        comparison = client.post("/api/hypotheses/ORION-001/compare", json={
            "hypothesis_ids": [first["id"], second["id"], third["id"]],
        })
        assert comparison.status_code == 200
        body = comparison.json()
        assert len(body["hypotheses"]) == 3
        assert body["disclaimer"] == "Current evidence comparison is exploratory and does not establish causation or determine the correct hypothesis."
        assert any("same underlying source" in insight for insight in body["insights"])
        matrix = {row["key"]: row for row in body["comparison_matrix"]}
        assert matrix["supporting"]["cells"][0]["value"] == 1
        assert matrix["contradicting"]["cells"][1]["value"] == 1
        current_first = client.get(f"/api/hypotheses/ORION-001/{first['id']}").json()["current_assessment"]
        assert matrix["assessment"]["cells"][0]["value"] == current_first
        assert matrix["assessment"]["cells"][2]["value"] == "NOT_YET_EVALUATED"
        assert body["hypotheses"][0]["evidence_counts"]["SUPPORTING"] == 1

        no_evidence = client.post("/api/hypotheses/ORION-001/compare", json={
            "hypothesis_ids": [third["id"], create_hypothesis(client, f"Compare D {fixture['tag']}")["id"]],
        })
        assert no_evidence.status_code == 200
        assert all(row["evidence_counts"]["total"] == 0 for row in no_evidence.json()["hypotheses"])

        other_investigation = create_hypothesis(client, f"Other investigation {fixture['tag']}", investigation="ORION-002")
        cross = client.post("/api/hypotheses/ORION-001/compare", json={
            "hypothesis_ids": [first["id"], other_investigation["id"]],
        })
        assert cross.status_code == 404
        same = client.post("/api/hypotheses/ORION-001/compare", json={"hypothesis_ids": [first["id"]]})
        assert same.status_code == 422


def test_impact_analysis_triggers_and_investigator_review():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        hypothesis = create_hypothesis(client, f"Impact {fixture['tag']}")
        before = client.get(f"/api/hypotheses/{hypothesis['id']}/impact").json()["total"]

        new_file = (
            '{"records":[{"person_id":"P-NEW-' + fixture["tag"] + '","event_date":"2024-06-25",'
            '"location_id":"LOC-NEW-' + fixture["tag"] + '","description":"Synthetic new evidence for impact analysis"}]}'
        ).encode()
        upload = client.post("/api/evidence/upload", files={
            "files": (f"impact-{fixture['tag']}.json", io.BytesIO(new_file), "application/json"),
        })
        assert upload.status_code == 200
        after = client.get(f"/api/hypotheses/{hypothesis['id']}/impact").json()
        assert after["total"] > before
        created = after["items"][0]
        assert created["impact_category"] == "REQUIRES_INVESTIGATOR_REVIEW"
        assert created["previous_assessment"] == created["current_assessment"]
        assert created["requires_review"] is True
        assert client.get(f"/api/hypotheses/ORION-001/{hypothesis['id']}").json()["status"] == "DRAFT"

        reviewed = client.post(f"/api/hypotheses/{hypothesis['id']}/impact/{created['impact_id']}/review", json={
            "reviewed_by": "pytest", "explanation": "No established relationship; reviewed and left unlinked.",
        })
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewed"] is True
        assert reviewed.json()["requires_review"] is False
        assert reviewed.json()["reviewed_by"] == "pytest"

        source_link = link(client, hypothesis["id"], "EXTRACTED_RECORD", fixture["records"][1]["record_id"], "CONTRADICTING")
        client.patch(f"/api/hypotheses/evidence/{source_link['link_id']}", json={
            "review_status": "VERIFIED", "evidence_strength": "STRONG",
        })
        impacts = client.get(f"/api/hypotheses/{hypothesis['id']}/impact", params={"page_size": 100}).json()["items"]
        assert any(item["trigger"] == "EVIDENCE_LINK_CREATED" for item in impacts)
        assert any(item["trigger"] == "EVIDENCE_LINK_UPDATED" for item in impacts)

        # Verifying an extracted record must re-evaluate linked hypotheses.
        record_id = fixture["records"][1]["record_id"]
        assert client.patch(f"/api/evidence/records/{record_id}/verify").status_code == 200
        refreshed = client.get(f"/api/hypotheses/{hypothesis['id']}/impact", params={"page_size": 100}).json()["items"]
        assert any(item["trigger"] == "EXTRACTED_RECORD_VERIFIED" for item in refreshed)

        # Reviewing a contradiction triggers impact analysis for linked hypotheses.
        contradiction = link(client, hypothesis["id"], "CONTRADICTION", fixture["contradiction"]["contradiction_id"], "CONTRADICTING")
        client.patch(f"/api/hypotheses/evidence/{contradiction['link_id']}", json={"review_status": "VERIFIED"})
        resolved = client.patch(f"/api/contradictions/{fixture['contradiction']['contradiction_id']}/review", json={
            "action": "RESOLVED", "review_note": "Synthetic test resolved the conflict.",
        })
        assert resolved.status_code == 200
        impacts_after = client.get(f"/api/hypotheses/{hypothesis['id']}/impact", params={"page_size": 200}).json()["items"]
        assert any(item["trigger"] == "CONTRADICTION_REVIEWED" for item in impacts_after)
        assessment = client.get(f"/api/hypotheses/{hypothesis['id']}/assessment").json()
        assert assessment["assessment_details"]["counts"]["unresolved_contradictions"] >= 0

        investigation_impacts = client.get("/api/hypotheses/ORION-001/impact", params={"page_size": 20})
        assert investigation_impacts.status_code == 200
        assert investigation_impacts.json()["total"] >= 1


def test_source_catalog_exposes_real_records_and_suggestions():
    with TestClient(app) as client:
        fixture = upload_fixture(client)
        hypothesis = create_hypothesis(client, f"Catalog {fixture['tag']}")
        catalog = client.get("/api/hypotheses/ORION-001/sources", params={"limit": 2000}).json()["items"]
        types = set()
        for source_type in ("EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT", "GRAPH_RELATIONSHIP", "CONTRADICTION"):
            typed = client.get("/api/hypotheses/ORION-001/sources", params={"source_type": source_type, "limit": 100}).json()["items"]
            if typed:
                types.add(source_type)
        assert {"EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT", "GRAPH_RELATIONSHIP", "CONTRADICTION"} <= types
        record = next(item for item in catalog
                      if item["source_type"] == "EXTRACTED_RECORD" and item["source_id"] == fixture["records"][0]["record_id"])
        assert record["title"]
        assert record["suggested_strength"] in {"STRONG", "MODERATE", "LIMITED", "INSUFFICIENT", "NOT_ASSESSED"}
        assert record["suggested_reliability"] in {"HIGH", "MODERATE", "LOW", "UNKNOWN", "NOT_ASSESSED"}
        assert record["suggested_strength_reason"]
        assert record["suggested_reliability_reason"]

        filtered = client.get("/api/hypotheses/ORION-001/sources", params={
            "source_type": "EXTRACTED_RECORD", "q": fixture["tag"], "hypothesis_id": hypothesis["id"],
        }).json()["items"]
        assert filtered and all(item["source_type"] == "EXTRACTED_RECORD" for item in filtered)
        assert all(item["already_linked"] is False for item in filtered)
        link(client, hypothesis["id"], "EXTRACTED_RECORD", filtered[0]["source_id"])
        refreshed = client.get("/api/hypotheses/ORION-001/sources", params={
            "source_type": "EXTRACTED_RECORD", "q": fixture["tag"], "hypothesis_id": hypothesis["id"],
        }).json()["items"]
        assert any(item["already_linked"] for item in refreshed)

        summary = client.get("/api/hypotheses/ORION-001/summary").json()
        assert summary["total_hypotheses"] >= 1
        assert "assessment_labels" in summary
