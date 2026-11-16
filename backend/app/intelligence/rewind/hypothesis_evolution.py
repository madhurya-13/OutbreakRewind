"""Historical evolution of a hypothesis from recorded versions and assessments."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import (Hypothesis, HypothesisAssessment, HypothesisEvidenceLink,
                       HypothesisReviewHistory, HypothesisVersion)
from .change_explainer import explain_assessment_change, explain_event
from .utils import aware, iso, loads, model_dict, parse_timestamp


def _hypothesis(db: Session, investigation_id: str, hypothesis_id: str) -> Hypothesis:
    item = db.get(Hypothesis, hypothesis_id)
    if not item or item.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Hypothesis not found in this investigation")
    return item


def hypothesis_evolution(
    investigation_id: str,
    hypothesis_id: str,
    db: Session,
    as_of_timestamp: str | datetime | None = None,
) -> dict[str, Any]:
    hypothesis = _hypothesis(db, investigation_id, hypothesis_id)
    cutoff = parse_timestamp(as_of_timestamp, field="as_of") if as_of_timestamp else None
    versions = list(db.scalars(select(HypothesisVersion).where(
        HypothesisVersion.hypothesis_id == hypothesis_id
    ).order_by(HypothesisVersion.created_at.asc())).all())
    if cutoff:
        versions = [item for item in versions if aware(item.created_at) <= cutoff]
    assessments = list(db.scalars(select(HypothesisAssessment).where(
        HypothesisAssessment.hypothesis_id == hypothesis_id
    ).order_by(HypothesisAssessment.evaluated_at.asc())).all())
    if cutoff:
        assessments = [item for item in assessments if aware(item.evaluated_at) <= cutoff]
    reviews = list(db.scalars(select(HypothesisReviewHistory).where(
        HypothesisReviewHistory.hypothesis_id == hypothesis_id
    ).order_by(HypothesisReviewHistory.created_at.asc())).all())
    if cutoff:
        reviews = [item for item in reviews if aware(item.created_at) <= cutoff]
    links = list(db.scalars(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis_id
    ).order_by(HypothesisEvidenceLink.created_at.asc())).all())
    if cutoff:
        links = [item for item in links if aware(item.created_at) <= cutoff]

    initial = loads(versions[0].snapshot_data, {}) if versions else {}
    assessment_entries = []
    for index, assessment in enumerate(assessments):
        previous = assessments[index - 1] if index else None
        previous_payload = model_dict(previous) if previous else None
        current_payload = model_dict(assessment)
        window_start = aware(previous.evaluated_at) if previous else None
        newly_linked = [model_dict(link) for link in links if (window_start is None or aware(link.created_at) >= window_start) and aware(link.created_at) <= aware(assessment.evaluated_at)]
        assessment_entries.append({
            **current_payload,
            "missing_information": loads(assessment.missing_information, []),
            "assessment_details": loads(assessment.assessment_details, {}),
            "previous_assessment": previous.assessment_label if previous else "NOT_YET_EVALUATED",
            "change_explanation": explain_assessment_change(previous_payload, current_payload, newly_linked) if previous else "Initial recorded qualitative assessment of the linked evidence.",
            "newly_linked_sources": newly_linked,
        })

    changes: list[dict[str, Any]] = []
    for version in versions:
        changes.append({
            "change_type": "VERSION_CREATED", "entity_type": "HYPOTHESIS_VERSION",
            "entity_id": f"{hypothesis_id}:v{version.version_number}", "occurred_at": iso(version.created_at),
            "description": version.change_description, "change_reason": version.reason,
            "actor": version.changed_by, "version_number": version.version_number,
            "state": loads(version.snapshot_data, {}),
        })
    for review in reviews:
        payload = model_dict(review)
        changes.append({
            "change_type": review.action, "entity_type": "HYPOTHESIS", "entity_id": hypothesis_id,
            "occurred_at": iso(review.created_at), "description": explain_event({
                "event_type": "HYPOTHESIS_STATUS_CHANGED" if review.action in {"STATUS_CHANGED", "ARCHIVED"} else "HYPOTHESIS_UPDATED",
                "entity_id": hypothesis_id, "actor_id": review.performed_by, "recorded_at": iso(review.created_at),
            }) + " " + (review.explanation or ""),
            "change_reason": review.explanation, "actor": review.performed_by,
            "previous_value": loads(review.previous_value, review.previous_value), "new_value": loads(review.new_value, review.new_value),
        })
    for link in links:
        changes.append({
            "change_type": "EVIDENCE_LINK_RECORDED", "entity_type": "HYPOTHESIS_EVIDENCE_LINK",
            "entity_id": link.id, "occurred_at": iso(link.created_at),
            "description": f"Linked source {link.source_title or link.source_id} as {link.classification}.",
            "change_reason": link.explanation, "actor": link.linked_by,
            "state": model_dict(link),
        })
    for assessment in assessment_entries:
        changes.append({
            "change_type": "ASSESSMENT_RECORDED", "entity_type": "HYPOTHESIS_ASSESSMENT",
            "entity_id": assessment.get("id") or assessment.get("assessment_id"), "occurred_at": assessment.get("evaluated_at"),
            "description": assessment["change_explanation"], "change_reason": "Deterministic reassessment against recorded evidence.",
            "actor": "system", "state": assessment,
        })
    changes.sort(key=lambda item: item.get("occurred_at") or "")
    latest_assessment = assessments[-1] if assessments else None
    return {
        "investigation_id": investigation_id, "hypothesis_id": hypothesis_id,
        "title": initial.get("title", hypothesis.title),
        "initial_creation": {
            "created_at": iso(hypothesis.created_at), "created_by": hypothesis.created_by,
            "assumptions": initial.get("assumptions", loads(hypothesis.assumptions, [])),
            "original_assessment": assessments[0].assessment_label if assessments else "NOT_YET_EVALUATED",
            "initial_version": versions[0].version_number if versions else None,
        },
        "versions": [{**model_dict(item), "snapshot_data": loads(item.snapshot_data, {}), "previous_data": loads(item.previous_data, {})} for item in versions],
        "assessments": assessment_entries,
        "assessment_table": [{
            "recorded_date": item.get("evaluated_at"), "assessment": item.get("assessment_label"),
            "change_explanation": item.get("change_explanation"),
        } for item in assessment_entries],
        "links": [model_dict(item) for item in links],
        "reviews": [model_dict(item) for item in reviews],
        "changes": changes,
        "current_assessment": latest_assessment.assessment_label if latest_assessment else "NOT_YET_EVALUATED",
        "as_of": cutoff.isoformat() if cutoff else None,
        "disclaimer": "Assessment evolution describes changes in available reviewed evidence, not proof that a hypothesis became scientifically correct.",
    }


def hypothesis_changes(investigation_id: str, hypothesis_id: str, db: Session) -> dict[str, Any]:
    evolution = hypothesis_evolution(investigation_id, hypothesis_id, db)
    return {
        "investigation_id": investigation_id, "hypothesis_id": hypothesis_id,
        "changes": evolution["changes"], "assessment_table": evolution["assessment_table"],
    }