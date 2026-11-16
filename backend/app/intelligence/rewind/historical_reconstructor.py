"""Point-in-time reconstruction of an investigation's recorded state."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import (Contradiction, ContradictionComparison, ContradictionEvidence,
                       ContradictionReview, EventAudit, EventSource, EvidenceRecord,
                       GraphNode, GraphRelationship, HistoricalEntityVersion,
                       Hypothesis, HypothesisAssessment, HypothesisEvidenceLink,
                       HypothesisNote, HypothesisReviewHistory, HypothesisVersion,
                       InvestigationHistoryEvent, InvestigationSnapshot,
                       ReconstructedEvent, RelationshipReviewHistory,
                       RelationshipSource, TemporalFinding, TemporalRelationship)
from .history_recorder import event_dict, event_module
from .utils import (INVESTIGATION_META, KNOWN_INVESTIGATIONS, aware, iso, loads,
                    model_dict, parse_timestamp, within)

PARTIAL_WARNING = (
    "Historical reconstruction is partially available because some records were not "
    "versioned when they were originally created."
)


def _require_investigation(investigation_id: str) -> None:
    if investigation_id not in KNOWN_INVESTIGATIONS:
        raise ValueError("Investigation not found")


def _versions(db: Session, investigation_id: str, cutoff: datetime) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    rows = db.scalars(select(HistoricalEntityVersion).where(
        HistoricalEntityVersion.investigation_id == investigation_id
    ).order_by(HistoricalEntityVersion.version_number.asc())).all()
    for row in rows:
        if within(row.recorded_at, cutoff):
            result[(row.entity_type, row.entity_id)] = {
                **model_dict(row),
                "state": loads(row.state_data, {}),
            }
    return result


def _coverage(db: Session, investigation_id: str, cutoff: datetime) -> dict[str, Any]:
    history = list(db.scalars(select(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id
    ).order_by(InvestigationHistoryEvent.recorded_at.asc())).all())
    versions = list(db.scalars(select(HistoricalEntityVersion).where(
        HistoricalEntityVersion.investigation_id == investigation_id
    ).order_by(HistoricalEntityVersion.recorded_at.asc())).all())
    tracked_moments = [aware(item.recorded_at) for item in history] + [aware(item.recorded_at) for item in versions]
    tracked_moments = [item for item in tracked_moments if item]
    tracked_since = min(tracked_moments) if tracked_moments else None
    evidence = list(db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all())
    events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all())
    hypotheses = list(db.scalars(select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)).all())
    untracked = {
        "evidence": sum(1 for item in evidence if tracked_since is None or (aware(item.uploaded_at) or tracked_since) < tracked_since),
        "timeline_events": sum(1 for item in events if tracked_since is None or (aware(item.created_at) or tracked_since) < tracked_since),
        "hypotheses": sum(1 for item in hypotheses if tracked_since is None or (aware(item.created_at) or tracked_since) < tracked_since),
    }
    has_history = bool(history)
    backfilled = [item for item in history if item.actor_id == "backfill" or bool(loads(item.metadata_json, {}).get("backfilled"))]
    partial = (not has_history) or any(untracked.values()) or cutoff < (tracked_since or cutoff) or bool(backfilled)
    warnings = [PARTIAL_WARNING] if partial else []
    if not has_history:
        warnings.append("No investigation history events exist for this investigation yet.")
    if backfilled:
        warnings.append(
            f"{len(backfilled)} history events were reconstructed from retained records because they predate active history tracking; "
            "their intermediate values may not be recoverable."
        )
    return {
        "status": "PARTIAL" if partial else "COMPLETE",
        "tracked_since": iso(tracked_since),
        "event_count": len([item for item in history if within(item.recorded_at, cutoff)]),
        "version_count": len([item for item in versions if within(item.recorded_at, cutoff)]),
        "unversioned_entity_counts": untracked,
        "backfilled_event_count": len(backfilled),
        "warnings": warnings,
        "reconstruction_note": (
            "Only information recorded at or before the selected cutoff is included. "
            "Unversioned older records fall back to their earliest available recorded state."
        ),
    }


def _evidence_state(db: Session, investigation_id: str, cutoff: datetime, versions: dict) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    rows = list(db.scalars(select(EvidenceRecord).where(
        EvidenceRecord.investigation_id == investigation_id
    ).order_by(EvidenceRecord.uploaded_at.asc())).all())
    history = list(db.scalars(select(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id,
        InvestigationHistoryEvent.entity_type.in_(["EVIDENCE_DOCUMENT", "EXTRACTED_RECORD"]),
    ).order_by(InvestigationHistoryEvent.recorded_at.asc())).all())
    record_events: dict[str, list[InvestigationHistoryEvent]] = defaultdict(list)
    for item in history:
        if within(item.recorded_at, cutoff):
            record_events[item.entity_id].append(item)
    evidence, records = [], []
    available_ids: set[str] = set()
    for item in rows:
        if not within(item.uploaded_at, cutoff):
            continue
        available_ids.add(item.id)
        version = versions.get(("EVIDENCE_DOCUMENT", item.id))
        state = version["state"] if version else {}
        status = state.get("status", item.status)
        for change in record_events.get(item.id, []):
            payload = loads(change.new_state, {})
            status = payload.get("status", status)
        evidence.append({
            "evidence_id": item.id, "filename": item.filename, "format": item.format,
            "status": status, "uploaded_at": iso(item.uploaded_at), "category": item.category,
            "checksum": item.checksum, "record_count": item.record_count,
            "processing_stage": item.processing_stage, "versioned": version is not None,
            "source_available": True,
        })
        for raw in loads(item.records_json, []):
            if not isinstance(raw, dict):
                continue
            record = dict(raw)
            record_id = str(record.get("record_id") or f"{item.id}_{len(records) + 1}")
            record["record_id"] = record_id
            record["evidence_id"] = item.id
            record.setdefault("verification_status", "PENDING")
            record_version = versions.get(("EXTRACTED_RECORD", record_id))
            if record_version:
                record.update(record_version["state"])
            for change in record_events.get(record_id, []):
                payload = loads(change.new_state, {})
                if isinstance(payload, dict):
                    record.update(payload)
            record["versioned"] = record_version is not None
            record["evidence_uploaded_at"] = iso(item.uploaded_at)
            records.append(record)
    return evidence, records, available_ids


def _timeline_state(db: Session, investigation_id: str, cutoff: datetime, available_evidence: set[str], versions: dict) -> dict[str, Any]:
    rows = list(db.scalars(select(ReconstructedEvent).where(
        ReconstructedEvent.investigation_id == investigation_id
    ).order_by(ReconstructedEvent.event_date.asc())).all())
    included = {row.event_id: row for row in rows if within(row.recorded_at, cutoff)}
    audits = list(db.scalars(select(EventAudit).where(
        EventAudit.event_id.in_(list(included.keys()) or ["__none__"])
    ).order_by(EventAudit.changed_at.asc())).all()) if included else []
    sources = list(db.scalars(select(EventSource).where(
        EventSource.event_id.in_(list(included.keys()) or ["__none__"])
    )).all()) if included else []
    sources_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sources:
        evidence_known = source.evidence_id in available_evidence
        if not evidence_known:
            evidence = db.get(EvidenceRecord, source.evidence_id)
            if evidence is not None:
                continue
        sources_by_event[source.event_id].append({**model_dict(source), "source_available": evidence_known})
    audits_by_event: dict[str, list[EventAudit]] = defaultdict(list)
    for audit in audits:
        if within(audit.changed_at, cutoff):
            audits_by_event[audit.event_id].append(audit)
    events = []
    for event_id, row in included.items():
        item = model_dict(row)
        version = versions.get(("RECONSTRUCTED_EVENT", event_id))
        if version:
            item.update(version["state"])
        for audit in audits_by_event.get(event_id, []):
            changes = loads(audit.new_value, {})
            if isinstance(changes, dict):
                item.update(changes)
            item.setdefault("audit_history", []).append({
                "actor": audit.actor, "changed_at": iso(audit.changed_at),
                "previous": loads(audit.previous_value, {}), "new": changes,
            })
        item["sources"] = sources_by_event.get(event_id, [])
        item["versioned"] = version is not None
        events.append(item)
    finding_rows = list(db.scalars(select(TemporalFinding).where(
        TemporalFinding.investigation_id == investigation_id
    ).order_by(TemporalFinding.created_at.asc())).all())
    findings = [model_dict(item) for item in finding_rows if within(item.created_at, cutoff) and (item.event_id is None or item.event_id in included)]
    relationships = list(db.scalars(select(TemporalRelationship).where(
        TemporalRelationship.event_id.in_(list(included.keys()) or ["__none__"])
    )).all()) if included else []
    relationships = [model_dict(item) for item in relationships if within(item.created_at, cutoff)]
    events.sort(key=lambda item: (item.get("event_date") is None, item.get("event_date") or "9999-12-31", item.get("event_id") or ""))
    return {
        "events": events, "findings": findings, "relationships": relationships,
        "summary": {
            "event_count": len(events),
            "verified_count": sum(str(item.get("verification_status")) == "VERIFIED" for item in events),
            "pending_review_count": sum(str(item.get("temporal_status")) in {"REQUIRES_REVIEW", "WARNING"} for item in events),
            "finding_count": len(findings),
        },
    }


def _network_state(db: Session, investigation_id: str, cutoff: datetime, available_evidence: set[str]) -> dict[str, Any]:
    relationships = list(db.scalars(select(GraphRelationship).where(
        GraphRelationship.investigation_id == investigation_id
    ).order_by(GraphRelationship.created_at.asc())).all())
    sources = list(db.scalars(select(RelationshipSource)).all())
    sources_by_relationship: dict[str, list[RelationshipSource]] = defaultdict(list)
    for source in sources:
        sources_by_relationship[source.relationship_id].append(source)
    reviews = list(db.scalars(select(RelationshipReviewHistory).order_by(RelationshipReviewHistory.action_timestamp.asc())).all())
    reviews_by_relationship: dict[str, list[RelationshipReviewHistory]] = defaultdict(list)
    for review in reviews:
        if within(review.action_timestamp, cutoff):
            reviews_by_relationship[review.relationship_id].append(review)
    included = []
    for item in relationships:
        if not within(item.created_at, cutoff):
            continue
        source_rows = sources_by_relationship.get(item.relationship_id, [])
        if any(row.evidence_id and row.evidence_id not in available_evidence for row in source_rows):
            continue
        status = "UNVERIFIED"
        for review in reviews_by_relationship.get(item.relationship_id, []):
            status = review.new_status
        included.append({
            **model_dict(item), "verification_status": status,
            "sources": [model_dict(row) for row in source_rows],
        })
    nodes = list(db.scalars(select(GraphNode).where(GraphNode.investigation_id == investigation_id)).all())
    referenced = {item["source_node_id"] for item in included} | {item["target_node_id"] for item in included}
    node_payload = [model_dict(item) for item in nodes if item.node_id in referenced and within(item.created_at, cutoff)]
    graph = nx.Graph()
    graph.add_nodes_from(item["node_id"] for item in node_payload)
    graph.add_edges_from((item["source_node_id"], item["target_node_id"]) for item in included)
    return {
        "nodes": node_payload,
        "relationships": included,
        "metrics": {
            "node_count": len(node_payload), "relationship_count": len(included),
            "connected_components": nx.number_connected_components(graph) if graph.number_of_nodes() else 0,
            "isolated_nodes": sum(degree == 0 for _, degree in graph.degree()),
            "verified_relationships": sum(item["verification_status"] == "VERIFIED" for item in included),
            "disputed_relationships": sum(item["verification_status"] == "REJECTED" for item in included),
        },
    }


def _contradiction_state(db: Session, investigation_id: str, cutoff: datetime, available_evidence: set[str]) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(Contradiction).where(
        Contradiction.investigation_id == investigation_id
    ).order_by(Contradiction.first_detected_at.asc())).all())
    reviews = list(db.scalars(select(ContradictionReview).order_by(ContradictionReview.created_at.asc())).all())
    comparisons = list(db.scalars(select(ContradictionComparison)).all())
    evidence = list(db.scalars(select(ContradictionEvidence)).all())
    reviews_by: dict[str, list[ContradictionReview]] = defaultdict(list)
    for review in reviews:
        if within(review.created_at, cutoff):
            reviews_by[review.contradiction_id].append(review)
    comparisons_by: dict[str, list[ContradictionComparison]] = defaultdict(list)
    for item in comparisons:
        comparisons_by[item.contradiction_id].append(item)
    evidence_by: dict[str, list[ContradictionEvidence]] = defaultdict(list)
    for item in evidence:
        if not item.evidence_id or item.evidence_id in available_evidence:
            evidence_by[item.contradiction_id].append(item)
    result = []
    for item in rows:
        if not within(item.first_detected_at, cutoff):
            continue
        status = "DETECTED"
        for review in reviews_by.get(item.contradiction_id, []):
            status = review.new_status
        result.append({
            **model_dict(item), "status": status,
            "comparisons": [model_dict(row) for row in comparisons_by.get(item.contradiction_id, [])],
            "evidence": [model_dict(row) for row in evidence_by.get(item.contradiction_id, [])],
            "reviews": [{**model_dict(row), "created_at": iso(row.created_at)} for row in reviews_by.get(item.contradiction_id, [])],
        })
    return result


def _hypothesis_state(db: Session, investigation_id: str, cutoff: datetime) -> list[dict[str, Any]]:
    hypotheses = list(db.scalars(select(Hypothesis).where(
        Hypothesis.investigation_id == investigation_id
    ).order_by(Hypothesis.created_at.asc())).all())
    versions = list(db.scalars(select(HypothesisVersion).order_by(HypothesisVersion.created_at.asc())).all())
    assessments = list(db.scalars(select(HypothesisAssessment).order_by(HypothesisAssessment.evaluated_at.asc())).all())
    reviews = list(db.scalars(select(HypothesisReviewHistory).order_by(HypothesisReviewHistory.created_at.asc())).all())
    links = list(db.scalars(select(HypothesisEvidenceLink).order_by(HypothesisEvidenceLink.created_at.asc())).all())
    notes = list(db.scalars(select(HypothesisNote).order_by(HypothesisNote.created_at.asc())).all())
    versions_by: dict[str, list[HypothesisVersion]] = defaultdict(list)
    for item in versions:
        if within(item.created_at, cutoff):
            versions_by[item.hypothesis_id].append(item)
    assessments_by: dict[str, list[HypothesisAssessment]] = defaultdict(list)
    for item in assessments:
        if within(item.evaluated_at, cutoff):
            assessments_by[item.hypothesis_id].append(item)
    reviews_by: dict[str, list[HypothesisReviewHistory]] = defaultdict(list)
    for item in reviews:
        if within(item.created_at, cutoff):
            reviews_by[item.hypothesis_id].append(item)
    links_by: dict[str, list[HypothesisEvidenceLink]] = defaultdict(list)
    for item in links:
        if within(item.created_at, cutoff):
            links_by[item.hypothesis_id].append(item)
    notes_by: dict[str, list[HypothesisNote]] = defaultdict(list)
    for item in notes:
        if within(item.created_at, cutoff):
            notes_by[item.hypothesis_id].append(item)
    result = []
    for hypothesis in hypotheses:
        if not within(hypothesis.created_at, cutoff):
            continue
        historical_versions = versions_by.get(hypothesis.id, [])
        latest_version = historical_versions[-1] if historical_versions else None
        state = loads(latest_version.snapshot_data, {}) if latest_version else {}
        links_for_hypothesis = links_by.get(hypothesis.id, [])
        if latest_version and isinstance(state.get("evidence_links"), list):
            links_payload = state["evidence_links"]
        else:
            links_payload = [{
                "link_id": item.id, "source_type": item.source_type, "source_id": item.source_id,
                "source_title": item.source_title, "classification": item.classification,
                "evidence_strength": item.evidence_strength, "source_reliability": item.source_reliability,
                "review_status": item.review_status, "explanation": item.explanation,
                "created_at": iso(item.created_at),
            } for item in links_for_hypothesis]
        latest_assessment = assessments_by.get(hypothesis.id, [])
        assessment = latest_assessment[-1] if latest_assessment else None
        item = {
            "hypothesis_id": hypothesis.id, "title": state.get("title", hypothesis.title),
            "category": state.get("category", hypothesis.category),
            "description": state.get("description", hypothesis.description),
            "status": state.get("status", hypothesis.status),
            "current_assessment": state.get("current_assessment", hypothesis.current_assessment),
            "current_version": state.get("current_version", latest_version.version_number if latest_version else hypothesis.current_version),
            "assumptions": state.get("assumptions", loads(hypothesis.assumptions, [])),
            "open_questions": state.get("open_questions", loads(hypothesis.open_questions, [])),
            "created_at": iso(hypothesis.created_at), "created_by": hypothesis.created_by,
            "updated_at": iso(hypothesis.updated_at),
            "evidence_links": links_payload,
            "assessment": ({**model_dict(assessment), "missing_information": loads(assessment.missing_information, []), "assessment_details": loads(assessment.assessment_details, {})} if assessment else None),
            "notes": [model_dict(note) for note in notes_by.get(hypothesis.id, [])],
            "version_count": len(historical_versions),
            "versioned": latest_version is not None,
            "review_history": [model_dict(row) for row in reviews_by.get(hypothesis.id, [])],
        }
        # Status transitions remain authoritative even when a content version did not change.
        for review in reviews_by.get(hypothesis.id, []):
            if review.action in {"STATUS_CHANGED", "ARCHIVED"}:
                item["status"] = review.new_value
        result.append(item)
    return result


def reconstruct_investigation_as_of(
    investigation_id: str,
    as_of_timestamp: str | datetime | None,
    db: Session,
) -> dict[str, Any]:
    """Reconstruct the investigation's recorded state at a UTC cutoff."""
    _require_investigation(investigation_id)
    cutoff = parse_timestamp(as_of_timestamp, field="as_of")
    versions = _versions(db, investigation_id, cutoff)
    coverage = _coverage(db, investigation_id, cutoff)
    evidence, records, available_evidence = _evidence_state(db, investigation_id, cutoff, versions)
    timeline = _timeline_state(db, investigation_id, cutoff, available_evidence, versions)
    network = _network_state(db, investigation_id, cutoff, available_evidence)
    contradictions = _contradiction_state(db, investigation_id, cutoff, available_evidence)
    hypotheses = _hypothesis_state(db, investigation_id, cutoff)
    history = list(db.scalars(select(InvestigationHistoryEvent).where(
        InvestigationHistoryEvent.investigation_id == investigation_id
    ).order_by(InvestigationHistoryEvent.recorded_at.asc())).all())
    history_payload = [event_dict(item) for item in history if within(item.recorded_at, cutoff)]
    snapshots = list(db.scalars(select(InvestigationSnapshot).where(
        InvestigationSnapshot.investigation_id == investigation_id
    ).order_by(InvestigationSnapshot.created_at.asc())).all())
    meta = dict(INVESTIGATION_META.get(investigation_id, {}))
    for event in history_payload:
        if event["event_type"] == "INVESTIGATION_STATUS_CHANGED":
            meta["status"] = event.get("new_state", {}).get("status", meta.get("status"))
    summary = {
        "evidence_count": len(evidence),
        "record_count": len(records),
        "event_count": timeline["summary"]["event_count"],
        "relationship_count": network["metrics"]["relationship_count"],
        "contradiction_count": len(contradictions),
        "unresolved_contradiction_count": sum(item["status"] not in {"RESOLVED", "DISMISSED"} for item in contradictions),
        "hypothesis_count": len(hypotheses),
        "active_hypothesis_count": sum(item["status"] != "ARCHIVED" for item in hypotheses),
        "temporal_finding_count": timeline["summary"]["finding_count"],
        "snapshot_count": len([item for item in snapshots if within(item.created_at, cutoff)]),
        "history_event_count": len(history_payload),
    }
    return {
        "investigation_id": investigation_id,
        "investigation": {
            "investigation_id": investigation_id,
            "investigation_name": meta.get("investigation_name", investigation_id),
            "description": meta.get("description", ""), "outbreak_category": meta.get("outbreak_category", "Unknown"),
            "status": meta.get("status", "Active"), "total_cases": meta.get("total_cases", 0),
        },
        "as_of": cutoff.isoformat(),
        "generated_at": iso(datetime.now(cutoff.tzinfo)),
        "mode": "HISTORICAL_READ_ONLY",
        "coverage": coverage,
        "summary": summary,
        "evidence": evidence,
        "records": records,
        "timeline": timeline,
        "network": network,
        "contradictions": contradictions,
        "hypotheses": hypotheses,
        "snapshots": [{"snapshot_id": item.snapshot_id, "snapshot_name": item.snapshot_name, "snapshot_type": item.snapshot_type, "event_cutoff": iso(item.event_cutoff), "created_at": iso(item.created_at)} for item in snapshots if within(item.created_at, cutoff)],
        "recent_changes": history_payload[-50:],
        "history": history_payload,
        "provenance": {
            "history_event_ids": [item["event_id"] for item in history_payload[-50:]],
            "source": "investigation_history_events + append-only entity versions + existing module snapshots/audits",
            "cutoff": cutoff.isoformat(),
            "future_information_excluded": True,
            "disclaimer": "This is a reconstruction of recorded information, not proof of transmission or disease causation.",
        },
    }


def coverage_for_investigation(investigation_id: str, db: Session, as_of_timestamp: str | datetime | None = None) -> dict[str, Any]:
    _require_investigation(investigation_id)
    cutoff = parse_timestamp(as_of_timestamp, field="as_of") if as_of_timestamp else datetime.now().astimezone()
    return _coverage(db, investigation_id, cutoff)