"""Evidence-to-hypothesis linking with provenance and duplicate protection."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Hypothesis, HypothesisEvidenceLink, HypothesisReviewHistory
from .constants import CLASSIFICATIONS, EVIDENCE_STRENGTHS, REVIEW_STATUSES, SOURCE_RELIABILITIES
from .evidence_assessor import default_strength_reason
from .evidence_impact_analyzer import create_impact_record, impact_category_for_classification
from .hypothesis_evaluator import evaluate_hypothesis, link_payload
from .hypothesis_versioning import hypothesis_snapshot, record_version
from .serializers import json_dumps, new_id, now
from .source_catalog import build_source_snapshot
from .source_reliability import default_reliability_reason


def _validate_choice(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise HTTPException(status_code=422, detail=f"Unsupported {field}")
    return value


def _explanation(value: str | None, minimum: int = 5) -> str:
    text = (value or "").strip()
    if len(text) < minimum:
        raise HTTPException(
            status_code=422,
            detail="An explanation is required for every evidence classification (at least 5 characters).",
        )
    return text[:5000]


def _review_history(
    db: Session, hypothesis_id: str, action: str, previous: Any, new: Any,
    explanation: str, actor: str, timestamp,
) -> None:
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=hypothesis_id,
        action=action,
        previous_value=json_dumps(previous) if not isinstance(previous, str) else previous,
        new_value=json_dumps(new) if not isinstance(new, str) else new,
        explanation=(explanation or "")[:5000],
        performed_by=actor or "investigator",
        created_at=timestamp,
    ))


def link_evidence(db: Session, hypothesis: Hypothesis, payload: dict[str, Any]) -> HypothesisEvidenceLink:
    source_type = _validate_choice(payload.get("source_type"), (
        "EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT", "GRAPH_RELATIONSHIP",
        "CONTRADICTION", "TEMPORAL_FINDING", "INVESTIGATOR_NOTE",
    ), "evidence source type")
    source_id = str(payload.get("source_id") or "").strip()
    if not source_id:
        raise HTTPException(status_code=422, detail="A source record ID is required")
    classification = _validate_choice(payload.get("classification"), CLASSIFICATIONS, "evidence classification")
    explanation = _explanation(payload.get("explanation"))
    strength = _validate_choice(payload.get("evidence_strength") or "NOT_ASSESSED", EVIDENCE_STRENGTHS, "evidence strength")
    reliability = _validate_choice(payload.get("source_reliability") or "NOT_ASSESSED", SOURCE_RELIABILITIES, "source reliability")

    snapshot = build_source_snapshot(db, hypothesis.investigation_id, source_type, source_id)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="Source record not found in this investigation. Link an existing Evidence Vault, timeline, network, contradiction, or temporal record.",
        )

    existing = db.scalar(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis.id,
        HypothesisEvidenceLink.source_type == source_type,
        HypothesisEvidenceLink.source_id == source_id,
    ))
    if existing:
        if existing.review_status == "WITHDRAWN":
            raise HTTPException(
                status_code=409,
                detail=(
                    "A withdrawn link already exists for this source. Restore that link instead of creating "
                    "a duplicate, so its audit history is preserved."
                ),
            )
        raise HTTPException(
            status_code=409,
            detail="This source is already linked to the hypothesis. Update the existing link instead of duplicating it.",
        )

    timestamp = now()
    actor = str(payload.get("linked_by") or "investigator")
    previous_hypothesis = hypothesis_snapshot(db, hypothesis)
    previous_assessment = hypothesis.current_assessment
    link = HypothesisEvidenceLink(
        id=new_id("HLNK"),
        hypothesis_id=hypothesis.id,
        source_type=source_type,
        source_id=source_id,
        source_title=(snapshot.get("title") or source_id)[:255],
        source_snapshot=json_dumps(snapshot),
        classification=classification,
        explanation=explanation,
        relevant_observations=str(payload.get("relevant_observations") or "").strip()[:5000],
        evidence_strength=strength,
        source_reliability=reliability,
        strength_reason=str(payload.get("strength_reason") or "").strip()[:5000] or default_strength_reason(strength, snapshot),
        reliability_reason=str(payload.get("reliability_reason") or "").strip()[:5000] or default_reliability_reason(reliability, snapshot),
        review_status="PENDING_REVIEW",
        investigator_notes=str(payload.get("investigator_notes") or "").strip()[:5000],
        linked_by=actor,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(link)
    db.flush()
    record_version(
        db, hypothesis, actor,
        f"Linked {source_type.replace('_', ' ').lower()} '{link.source_title}' as {classification}.",
        reason=explanation,
        previous_data=previous_hypothesis,
    )
    _review_history(
        db, hypothesis.id, "EVIDENCE_LINK_CREATED",
        {"link_id": link.id, "source": source_id, "classification": None},
        {"link_id": link.id, "source": source_id, "classification": classification},
        explanation, actor, timestamp,
    )
    assessment = evaluate_hypothesis(db, hypothesis, evaluated_by=actor)
    create_impact_record(
        db, hypothesis, source_type, source_id, previous_assessment, assessment.assessment_label,
        f"Source '{link.source_title}' was linked as {classification}. The hypothesis assessment was recalculated. "
        "This remains an investigator-controlled review item.",
        category=impact_category_for_classification(classification),
        trigger="EVIDENCE_LINK_CREATED",
    )
    return link


def update_link(db: Session, link: HypothesisEvidenceLink, hypothesis: Hypothesis, payload: dict[str, Any]) -> HypothesisEvidenceLink:
    updates = {key: value for key, value in payload.items() if value is not None and key not in {"updated_by"}}
    if not updates:
        raise HTTPException(status_code=422, detail="No evidence-link fields were supplied")
    if "classification" in updates:
        _validate_choice(updates["classification"], CLASSIFICATIONS, "evidence classification")
    if "evidence_strength" in updates:
        _validate_choice(updates["evidence_strength"], EVIDENCE_STRENGTHS, "evidence strength")
    if "source_reliability" in updates:
        _validate_choice(updates["source_reliability"], SOURCE_RELIABILITIES, "source reliability")
    if "review_status" in updates:
        _validate_choice(updates["review_status"], REVIEW_STATUSES, "review status")
    if "explanation" in updates:
        updates["explanation"] = _explanation(updates["explanation"])
    if "review_status" in updates and updates["review_status"] == "WITHDRAWN" and link.review_status == "WITHDRAWN":
        raise HTTPException(status_code=409, detail="Evidence link is already withdrawn")

    snapshot = build_source_snapshot(db, hypothesis.investigation_id, link.source_type, link.source_id)
    actor = str(payload.get("updated_by") or "investigator")
    timestamp = now()
    previous_values = {
        key: getattr(link, key)
        for key in ("classification", "explanation", "evidence_strength", "source_reliability",
                    "strength_reason", "reliability_reason", "review_status", "investigator_notes")
    }
    previous_hypothesis = hypothesis_snapshot(db, hypothesis)
    previous_assessment = hypothesis.current_assessment

    for key, value in updates.items():
        if key in {"strength_reason", "reliability_reason", "investigator_notes", "relevant_observations"}:
            value = str(value)[:5000]
        setattr(link, key, value)
    if not link.strength_reason:
        link.strength_reason = default_strength_reason(link.evidence_strength, snapshot)
    if not link.reliability_reason:
        link.reliability_reason = default_reliability_reason(link.source_reliability, snapshot)
    if link.review_status in {"VERIFIED", "REVIEWED", "DISPUTED", "WITHDRAWN"}:
        link.reviewed_by = actor
        link.reviewed_at = timestamp
    link.updated_at = timestamp

    change_text = ", ".join(sorted(updates.keys()))
    record_version(
        db, hypothesis, actor,
        f"Updated evidence link '{link.source_title}': {change_text}.",
        reason=str(payload.get("investigator_notes") or ""),
        previous_data=previous_hypothesis,
    )
    _review_history(
        db, hypothesis.id, "EVIDENCE_LINK_UPDATED", previous_values,
        {key: getattr(link, key) for key in previous_values},
        str(payload.get("investigator_notes") or ""), actor, timestamp,
    )
    assessment = evaluate_hypothesis(db, hypothesis, evaluated_by=actor)
    create_impact_record(
        db, hypothesis, link.source_type, link.source_id, previous_assessment, assessment.assessment_label,
        f"Evidence link '{link.source_title}' changed ({change_text}). The hypothesis assessment was recalculated; "
        "the investigator retains control of the hypothesis status.",
        category=(
            "NO_CLEAR_IMPACT" if link.review_status == "WITHDRAWN"
            else impact_category_for_classification(link.classification)
        ),
        trigger="EVIDENCE_LINK_UPDATED",
        requires_review=True,
    )
    return link


def withdraw_link(db: Session, link: HypothesisEvidenceLink, hypothesis: Hypothesis, actor: str = "investigator") -> HypothesisEvidenceLink:
    if link.review_status == "WITHDRAWN":
        raise HTTPException(status_code=409, detail="Evidence link is already withdrawn")
    timestamp = now()
    previous_hypothesis = hypothesis_snapshot(db, hypothesis)
    previous_assessment = hypothesis.current_assessment
    previous_status = link.review_status
    link.review_status = "WITHDRAWN"
    link.reviewed_by = actor
    link.reviewed_at = timestamp
    link.updated_at = timestamp
    record_version(
        db, hypothesis, actor,
        f"Withdrew evidence link '{link.source_title}'; audit history retained.",
        reason="Evidence link withdrawn by investigator.",
        previous_data=previous_hypothesis,
    )
    _review_history(
        db, hypothesis.id, "EVIDENCE_LINK_WITHDRAWN", previous_status, "WITHDRAWN",
        "Link withdrawn; record retained for audit.", actor, timestamp,
    )
    assessment = evaluate_hypothesis(db, hypothesis, evaluated_by=actor)
    create_impact_record(
        db, hypothesis, link.source_type, link.source_id, previous_assessment, assessment.assessment_label,
        f"Evidence link '{link.source_title}' was withdrawn. The source record itself was not deleted, and the "
        "previous link and assessment remain in history.",
        category="NO_CLEAR_IMPACT", trigger="EVIDENCE_LINK_WITHDRAWN", requires_review=True,
    )
    return link


def list_links(
    db: Session,
    hypothesis: Hypothesis,
    classification: str | None = None,
    review_status: str | None = None,
    source_type: str | None = None,
    include_withdrawn: bool = True,
) -> list[dict[str, Any]]:
    links = list(db.scalars(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis.id
    ).order_by(HypothesisEvidenceLink.created_at.desc())).all())
    if classification:
        links = [link for link in links if link.classification == classification]
    if review_status:
        links = [link for link in links if link.review_status == review_status]
    if source_type:
        links = [link for link in links if link.source_type == source_type]
    if not include_withdrawn:
        links = [link for link in links if link.review_status != "WITHDRAWN"]
    return [link_payload(db, hypothesis, link) for link in links]
