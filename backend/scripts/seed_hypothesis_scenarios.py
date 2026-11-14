"""Seed the synthetic Project ORION competing-hypothesis scenarios.

Run this against a running API after the database is migrated:

    cd backend
    python scripts/seed_hypothesis_scenarios.py

The script uploads only synthetic data, reuses the Milestone 2-5 ingestion,
timeline, graph, and contradiction pipeline, and links hypotheses to actual
source record IDs discovered from the API. It is idempotent: if the scenario
hypotheses already exist it exits without creating duplicates.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

BASE_URL = os.environ.get("ORION_API_URL", "http://localhost:8000")
INVESTIGATION = "ORION-001"
ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FILE = ROOT / "synthetic_data" / "hypothesis_orion.json"
CORRECTION_FILE = ROOT / "synthetic_data" / "hypothesis_orion_correction.json"


def fail(response: httpx.Response) -> None:
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = response.text
    raise SystemExit(f"{response.request.method} {response.request.url} failed ({response.status_code}): {detail}")


def call(client: httpx.Client, method: str, path: str, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        fail(response)
    return response.json() if response.content else {}


def upload(client: httpx.Client, path: Path) -> dict:
    with path.open("rb") as handle:
        response = client.post(
            "/api/evidence/upload",
            files={"files": (path.name, handle, "application/json")},
            data={"investigation_id": INVESTIGATION, "category": "Investigator Observation"},
        )
    if response.status_code in {409, 415} and "already been uploaded" in response.text:
        print(f"  · {path.name} already ingested; reusing existing records")
        return {}
    if response.status_code >= 400:
        fail(response)
    return response.json()


def source_catalog(client: httpx.Client) -> list[dict]:
    """Fetch each source type separately so a large investigation cannot
    truncate later source types from a single combined catalogue response."""
    items: list[dict] = []
    for source_type in (
        "EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT",
        "GRAPH_RELATIONSHIP", "CONTRADICTION", "TEMPORAL_FINDING",
    ):
        response = call(client, "GET", f"/api/hypotheses/{INVESTIGATION}/sources", params={
            "source_type": source_type, "limit": 2000,
        })
        items.extend(response["items"])
    return items


def pick(items: list[dict], source_type: str, **details) -> dict | None:
    for item in items:
        if item["source_type"] != source_type:
            continue
        payload = item.get("details") or {}
        if all(str(payload.get(key) or "") == str(value) for key, value in details.items()):
            return item
    return None


def pick_contains(items: list[dict], source_type: str, text: str) -> dict | None:
    for item in items:
        if item["source_type"] == source_type:
            haystack = f"{item.get('title')} {item.get('subtitle')} {item.get('details')}".lower()
            if text.lower() in haystack:
                return item
    return None


def link(
    client: httpx.Client,
    hypothesis_id: str,
    source: dict | None,
    classification: str,
    explanation: str,
    strength: str,
    reliability: str,
    review_status: str = "PENDING_REVIEW",
    observations: str = "",
    notes: str = "",
) -> dict | None:
    if not source:
        print(f"  ! required source unavailable for {classification}; skipped")
        return None
    response = client.post(f"/api/hypotheses/{hypothesis_id}/evidence", json={
        "source_type": source["source_type"],
        "source_id": source["source_id"],
        "classification": classification,
        "explanation": explanation,
        "evidence_strength": strength,
        "source_reliability": reliability,
        "strength_reason": f"Selected because the linked {source['source_type'].replace('_', ' ').lower()} "
                           f"is {'verified' if source.get('verification_status') == 'VERIFIED' else 'traceable but ' + str(source.get('verification_status', 'unverified')).lower()} "
                           "and is directly relevant to this particular hypothesis.",
        "reliability_reason": f"Reliability was judged from the source's provenance and verification status "
                              f"({source.get('verification_status', 'UNKNOWN')}), independently of whether it supports the hypothesis.",
        "relevant_observations": observations,
        "investigator_notes": notes,
        "linked_by": "seed-investigator",
    })
    if response.status_code == 409 and "already linked" in response.text:
        existing = call(client, "GET", f"/api/hypotheses/{hypothesis_id}/evidence")
        return next((item for item in existing
                     if item["source_type"] == source["source_type"] and item["source_id"] == source["source_id"]), None)
    if response.status_code >= 400:
        fail(response)
    link_payload = response.json()
    if review_status != "PENDING_REVIEW":
        call(client, "PATCH", f"/api/hypotheses/evidence/{link_payload['link_id']}", json={
            "review_status": review_status,
            "investigator_notes": notes or f"Marked {review_status.lower()} during the synthetic scenario seed.",
        })
    return link_payload


def set_status(client: httpx.Client, hypothesis_id: str, status: str, explanation: str) -> None:
    call(client, "PATCH", f"/api/hypotheses/{hypothesis_id}/status", json={
        "status": status, "explanation": explanation, "updated_by": "seed-investigator",
    })


def create_hypothesis(client: httpx.Client, payload: dict) -> dict:
    return call(client, "POST", f"/api/hypotheses/{INVESTIGATION}", json=payload)


def main() -> None:
    if not SCENARIO_FILE.exists():
        raise SystemExit(f"Missing scenario fixture: {SCENARIO_FILE}")

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        call(client, "GET", "/api/health")
        existing = call(client, "GET", f"/api/hypotheses/{INVESTIGATION}", params={"page_size": 100})
        if any(item["title"] == "Shared exposure at the North Quay depot" for item in existing["items"]):
            print("Project ORION hypothesis scenarios already exist; nothing to seed.")
            return

        print("1. Ingesting synthetic ORION scenario evidence…")
        upload(client, SCENARIO_FILE)
        call(client, "POST", f"/api/timeline/reconstruct/{INVESTIGATION}")
        call(client, "POST", f"/api/graph/rebuild/{INVESTIGATION}")
        call(client, "POST", f"/api/contradictions/detect/{INVESTIGATION}")

        catalog = source_catalog(client)
        print(f"   · {len(catalog)} existing investigation sources available for linking")

        evidence_doc = pick_contains(catalog, "EVIDENCE_DOCUMENT", "hypothesis_orion.json")
        record_p101 = pick(catalog, "EXTRACTED_RECORD", person_id="P101")
        record_p102 = pick(catalog, "EXTRACTED_RECORD", person_id="P102")
        record_p107 = pick(catalog, "EXTRACTED_RECORD", person_id="P107")
        record_p108 = pick(catalog, "EXTRACTED_RECORD", person_id="P108")
        record_p110 = pick(catalog, "EXTRACTED_RECORD", person_id="P110")
        event_p110 = next((item for item in catalog
                           if item["source_type"] == "RECONSTRUCTED_EVENT"
                           and (item.get("details") or {}).get("person_id") == "P110"), None)
        direct_contact = next((item for item in catalog
                               if item["source_type"] == "GRAPH_RELATIONSHIP"
                               and (item.get("details") or {}).get("relationship_type") == "DIRECT_CONTACT"
                               and "P101" in f"{item.get('details', {}).get('source_label')} {item.get('details', {}).get('target_label')}"
                               and "P102" in f"{item.get('details', {}).get('source_label')} {item.get('details', {}).get('target_label')}"), None)
        contradiction_date = pick(catalog, "CONTRADICTION", contradiction_type="DATE_CONFLICT")
        contradiction_location = pick(catalog, "CONTRADICTION", contradiction_type="LOCATION_CONFLICT")
        contradiction_lab = pick(catalog, "CONTRADICTION", contradiction_type="LAB_RESULT_CONFLICT")
        temporal_finding = next((item for item in catalog if item["source_type"] == "TEMPORAL_FINDING"), None)

        print("2. Creating four competing hypotheses…")
        hypothesis_a = create_hypothesis(client, {
            "title": "Shared exposure at the North Quay depot",
            "category": "SHARED_LOCATION_EXPOSURE",
            "description": "Several early cases may share a common exposure at the North Quay depot rather than transmitting only within households.",
            "detailed_explanation": "The proposed sequence begins with one or more visits to the North Quay depot, followed by symptom onset among attendees and their household contacts. The explanation predicts overlapping location visits and similar exposure dates for several people.",
            "assumptions": ["The reported depot visit dates are approximately accurate.", "LOC-01 and LOC-02 refer to the same physical depot complex."],
            "predictions": ["Independent cases should report a depot visit before onset.", "Household contacts should not explain every early case."],
            "limitations": ["Location records are interview-based and may be incomplete.", "Visits do not prove exposure or transmission."],
            "open_questions": ["Which verified records place each early case at the depot?", "Do the conflicting visit reports describe different entrances or dates?"],
            "initial_notes": "Synthetic ORION scenario. This is a competing explanation, not an established transmission chain.",
            "created_by": "seed-investigator",
        })
        hypothesis_b = create_hypothesis(client, {
            "title": "Household contact chain from the index case",
            "category": "PERSON_TO_PERSON_CONTACT",
            "description": "A sequence of reported household and direct contacts may explain the early case relationships.",
            "detailed_explanation": "The index case is proposed to have exposed a household contact during a defined interval. The explanation predicts explicit contact records and reconstructed events that precede the contact's symptom onset.",
            "assumptions": ["The explicit contact record is accurate.", "Contact occurred before the secondary case's onset."],
            "predictions": ["A verified direct-contact relationship should exist.", "The contact date should precede the secondary case's symptom onset."],
            "limitations": ["Contact records describe reported contact, not proven transmission.", "Recall and date errors are possible."],
            "open_questions": ["Is the contact interval consistent with the reconstructed timeline?", "Are there unrecorded contacts in the same household?"],
            "initial_notes": "Synthetic ORION scenario for direct contact reasoning.",
            "created_by": "seed-investigator",
        })
        hypothesis_c = create_hypothesis(client, {
            "title": "Multiple independent introductions",
            "category": "MULTIPLE_INDEPENDENT_SOURCES",
            "description": "The observed cases may reflect more than one independent exposure source rather than a single connected cluster.",
            "detailed_explanation": "Distinct location records and separate relationship groups could indicate several introductions into the area. The explanation predicts separate exposure timelines and weak connectivity between groups.",
            "assumptions": ["The separate location reports describe genuinely distinct exposures.", "Missing links between groups are not simply unrecorded."],
            "predictions": ["Separate groups should have distinct location histories.", "No verified relationship should connect every group."],
            "limitations": ["Absence of a recorded link is not evidence of independence.", "The available records do not yet cover all cases."],
            "open_questions": ["Are the East Ridge market reports independent of the depot cluster?", "What evidence would connect or separate the groups?"],
            "initial_notes": "Synthetic ORION scenario. Evidence is intentionally provisional.",
            "created_by": "seed-investigator",
        })
        hypothesis_d = create_hypothesis(client, {
            "title": "Reporting and data inconsistency",
            "category": "REPORTING_OR_DATA_ERROR",
            "description": "Some apparent relationships may result from delayed reporting, duplicated records, inconsistent dates, or conflicting source values.",
            "detailed_explanation": "The explanation proposes that several apparent links are artefacts of reporting quality. It predicts detectable contradictions, duplicate sample identifiers, ambiguous dates, and corrected records.",
            "assumptions": ["At least some contradictions reflect reporting error rather than true differences.", "Original verified records can establish a consistent sequence."],
            "predictions": ["Contradiction findings should concentrate in a small number of records.", "Verified original records should resolve some conflicts."],
            "limitations": ["A detected contradiction is not proof that a source is false.", "Corrections may themselves introduce new inconsistencies."],
            "open_questions": ["Which conflicts survive review of the original documents?", "Are the duplicated sample identifiers the same specimen?"],
            "initial_notes": "Synthetic ORION scenario. Contradictions are review candidates, not automatic errors.",
            "created_by": "seed-investigator",
        })

        print("3. Linking actual ORION source records…")
        link(client, hypothesis_a["id"], record_p101, "SUPPORTING",
             "The extracted record explicitly places P101 at LOC-01 on the proposed exposure date.",
             "MODERATE", "HIGH", "REVIEWED",
             observations="P101 · LOC-01 · 2024-06-02", notes="Reviewed against the original extracted row.")
        link(client, hypothesis_a["id"], evidence_doc, "CONTEXTUAL",
             "The uploaded scenario document provides investigation background but does not itself establish the depot exposure.",
             "LIMITED", "MODERATE", "PENDING_REVIEW",
             observations="Scenario background document.")
        link(client, hypothesis_a["id"], temporal_finding, "NEUTRAL",
             "The temporal finding is a review prompt and does not distinguish between shared-location and contact explanations.",
             "LIMITED", "MODERATE", "PENDING_REVIEW")
        link(client, hypothesis_a["id"], contradiction_date, "CONTRADICTING",
             "Conflicting source dates weaken the assumption that reported depot visit dates are reliable.",
             "MODERATE", "LOW", "PENDING_REVIEW",
             observations="Field-level date comparison under review.")

        link(client, hypothesis_b["id"], record_p102, "SUPPORTING",
             "The record explicitly names P101 as a household contact of P102 before the secondary onset.",
             "STRONG", "HIGH", "VERIFIED",
             observations="P102 · contact P101 · 2024-06-03")
        link(client, hypothesis_b["id"], direct_contact, "SUPPORTING",
             "The Case Network contains an explicit direct-contact relationship between P101 and P102.",
             "MODERATE", "HIGH", "VERIFIED",
             observations="DIRECT_CONTACT · explicit derivation")
        link(client, hypothesis_b["id"], event_p110 or record_p110, "CONTRADICTING",
             "This record reports a depot visit after the recorded onset, which conflicts with the proposed contact-before-onset sequence.",
             "MODERATE", "MODERATE", "REVIEWED",
             observations="Timing requires investigator review.")
        link(client, hypothesis_b["id"], record_p110, "NEUTRAL",
             "The incomplete contact details neither confirm nor contradict the proposed household chain.",
             "LIMITED", "LOW", "PENDING_REVIEW")

        link(client, hypothesis_c["id"], record_p107, "SUPPORTING",
             "The record reports an East Ridge market exposure separate from the depot cluster.",
             "MODERATE", "MODERATE", "PENDING_REVIEW",
             observations="P107 · LOC-04 · 2024-06-08")
        link(client, hypothesis_c["id"], record_p108, "CONTEXTUAL",
             "A second East Ridge market report adds context for the independent-source explanation but is unverified.",
             "LIMITED", "MODERATE", "PENDING_REVIEW")
        link(client, hypothesis_c["id"], evidence_doc, "NEUTRAL",
             "The background document does not distinguish independent introductions from a single connected cluster.",
             "LIMITED", "MODERATE", "PENDING_REVIEW")

        link(client, hypothesis_d["id"], contradiction_location, "SUPPORTING",
             "The location conflict is consistent with the proposed reporting inconsistency and contains field-level comparisons.",
             "MODERATE", "MODERATE", "VERIFIED",
             observations="Conflicting location reports for the same person.")
        link(client, hypothesis_d["id"], contradiction_lab, "SUPPORTING",
             "The conflicting laboratory result and duplicated accession are consistent with a data-quality explanation.",
             "MODERATE", "LOW", "VERIFIED",
             observations="Duplicated sample identifier with conflicting result.")
        link(client, hypothesis_d["id"], record_p102, "CONTRADICTING",
             "The verified original record provides a consistent contact sequence, which limits a broad data-error explanation.",
             "MODERATE", "HIGH", "REVIEWED")
        link(client, hypothesis_d["id"], temporal_finding, "CONTEXTUAL",
             "The temporal finding flags a review candidate but does not establish that the cluster is a reporting artefact.",
             "LIMITED", "MODERATE", "PENDING_REVIEW")

        print("4. Verifying source records and recording investigator status decisions…")
        # Verify the two key extracted records so reliability is traceable. This
        # also exercises the impact hook for verified extracted records.
        for record in (record_p101, record_p102):
            if record:
                client.patch(f"/api/evidence/records/{record['source_id']}/verify", params={"verified": "true"})
        if direct_contact:
            client.patch(f"/api/graph/relationships/{direct_contact['source_id']}/review", json={
                "verification_status": "VERIFIED", "reviewer_note": "Synthetic scenario review of the explicit contact edge.",
            })
        set_status(client, hypothesis_a["id"], "UNDER_INVESTIGATION", "Depot exposure remains a competing explanation.")
        set_status(client, hypothesis_b["id"], "UNDER_INVESTIGATION", "Direct contact chain is being tested against the timeline.")
        set_status(client, hypothesis_d["id"], "UNDER_INVESTIGATION", "Data-quality explanation is under active review.")

        print("5. Running the investigation-wide evaluation…")
        evaluation = call(client, "POST", f"/api/hypotheses/evaluate/{INVESTIGATION}")
        for item in evaluation["items"]:
            print(f"   - {item['title']}: {item['previous_assessment']} -> {item['assessment']['assessment_label']}")

        print("6. Uploading a new corrected source to trigger impact analysis…")
        upload(client, CORRECTION_FILE)
        call(client, "POST", f"/api/timeline/reconstruct/{INVESTIGATION}")
        impacts = call(client, "GET", f"/api/hypotheses/{INVESTIGATION}/impact", params={"page_size": 100})
        print(f"   · {impacts['total']} impact records available; {sum(1 for i in impacts['items'] if i['requires_review'])} require review")

        correction = call(client, "GET", "/api/evidence", params={"investigation_id": INVESTIGATION})
        correction_item = next((item for item in correction if item["source"] == CORRECTION_FILE.name), None)
        if correction_item:
            rows = call(client, "GET", f"/api/evidence/{correction_item['evidence_id']}/records")["records"]
            if rows:
                record_id = rows[0]["record_id"]
                client.patch(f"/api/evidence/records/{record_id}/verify", params={"verified": "true"})
                refreshed = source_catalog(client)
                correction_record = next((item for item in refreshed
                                          if item["source_type"] == "EXTRACTED_RECORD" and item["source_id"] == record_id), None)
                before = call(client, "GET", f"/api/hypotheses/{INVESTIGATION}/{hypothesis_a['id']}")
                link(client, hypothesis_a["id"], correction_record, "SUPPORTING",
                     "The newly corrected record independently confirms the depot visit and household contact on the same date.",
                     "STRONG", "HIGH", "VERIFIED",
                     observations="Correction document · P101 · LOC-01 · 2024-06-02")
                after = call(client, "POST", f"/api/hypotheses/{hypothesis_a['id']}/evaluate")
                print(f"   - Depot hypothesis assessment: {before['current_assessment']} -> {after['assessment_label']}")

        print("7. Recording one investigator review and one note…")
        pending = call(client, "GET", f"/api/hypotheses/{hypothesis_a['id']}/impact",
                       params={"reviewed": "false", "page_size": 20})["items"]
        if pending:
            call(client, "POST", f"/api/hypotheses/{hypothesis_a['id']}/impact/{pending[0]['impact_id']}/review", json={
                "reviewed_by": "seed-investigator",
                "explanation": "Reviewed the new source; it was linked as supporting evidence and remains subject to investigator judgment.",
            })
        call(client, "POST", f"/api/hypotheses/{hypothesis_b['id']}/notes", json={
            "note": "Synthetic scenario note: confirm the contact interval against the reconstructed onset before changing status.",
            "created_by": "seed-investigator",
        })

        summary = call(client, "GET", f"/api/hypotheses/{INVESTIGATION}/summary")
        print("\nSeed complete.")
        print(f"  · {summary['total_hypotheses']} hypotheses")
        print(f"  · {summary['with_supporting_evidence']} with supporting evidence")
        print(f"  · {summary['significant_contradictions']} with significant contradictions")
        print(f"  · {summary['requiring_review']} outstanding review items")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print(f"Could not reach {BASE_URL}. Start the FastAPI server first.", file=sys.stderr)
        raise SystemExit(1)
