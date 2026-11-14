"""New-evidence impact analysis and investigator review of impact records."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Hypothesis, HypothesisEvidenceLink, HypothesisImpactRecord, HypothesisReviewHistory
from .constants import IMPACT_CATEGORIES
from .hypothesis_evaluator import evaluate_hypothesis
from .serializers import new_id, now
from .source_catalog import build_source_snapshot


def impact_category_for_classification(classification: str) -> str:
    return {
        "SUPPORTING": "POTENTIALLY_SUPPORTS",
        "CONTRADICTING": "POTENTIALLY_CONTRADICTS",
        "NEUTRAL": "ADDS_CONTEXT",
        "CONTEXTUAL": "ADDS_CONTEXT",
    }.get(classification, "REQUIRES_INVESTIGATOR_REVIEW")


def create_impact_record(
    db: Session,
    hypothesis: Hypothesis,
    source_type: str,
    source_id: str,
    previous_assessment: str,
    current_assessment: str,
    explanation: str,
    category: str = "REQUIRES_INVESTIGATOR_REVIEW",
    trigger: str = "",
    requires_review: bool = True,
) -> HypothesisImpactRecord:
    if category not in IMPACT_CATEGORIES:
        category = "REQUIRES_INVESTIGATOR_REVIEW"
    record = HypothesisImpactRecord(
        id=new_id("HIMP"),
        hypothesis_id=hypothesis.id,
        source_type=source_type,
        source_id=source_id,
        impact_category=category,
        previous_assessment=previous_assessment,
        current_assessment=current_assessment,
        explanation=explanation,
        trigger=trigger,
        requires_review=requires_review,
        reviewed=not requires_review,
        created_at=now(),
    )
    db.add(record)
    return record


def analyze_source_change(
    db: Session,
    investigation_id: str,
    source_type: str,
    source_id: str,
    trigger: str,
    include_unlinked: bool = True,
    only_linked: bool = False,
) -> list[HypothesisImpactRecord]:
    """Identify hypotheses affected by a new or changed source.

    The engine never decides whether a newly uploaded source supports or
    contradicts a hypothesis. If no link exists it creates an investigator-review
    item. If a link exists, it re-runs the deterministic evaluation and stores the
    previous and resulting labels.
    """
    snapshot = build_source_snapshot(db, investigation_id, source_type, source_id)
    hypotheses = list(db.scalars(select(Hypothesis).where(
        Hypothesis.investigation_id == investigation_id,
        Hypothesis.status != "ARCHIVED",
    )).all())
    records: list[HypothesisImpactRecord] = []
    for hypothesis in hypotheses:
        links = list(db.scalars(select(HypothesisEvidenceLink).where(
            HypothesisEvidenceLink.hypothesis_id == hypothesis.id,
            HypothesisEvidenceLink.source_type == source_type,
            HypothesisEvidenceLink.source_id == source_id,
            HypothesisEvidenceLink.review_status != "WITHDRAWN",
        )).all())
        previous = hypothesis.current_assessment
        source_title = (snapshot or {}).get("title") or source_id
        if links:
            assessment = evaluate_hypothesis(db, hypothesis, evaluated_by=f"impact:{trigger.lower()}")
            current = assessment.assessment_label
            categories = {impact_category_for_classification(link.classification) for link in links}
            category = categories.pop() if len(categories) == 1 else "REQUIRES_INVESTIGATOR_REVIEW"
            explanation = (
                f"{source_type.replace('_', ' ').title()} '{source_title}' is already linked to this hypothesis "
                f"as {links[0].classification}. The evaluation was recalculated after {trigger.lower().replace('_', ' ')}. "
                f"Previous assessment: {previous}. Current assessment: {current}. "
                "This is a review prompt, not an automatic conclusion."
            )
            records.append(create_impact_record(
                db, hypothesis, source_type, source_id, previous, current, explanation,
                category=category, trigger=trigger,
            ))
        elif include_unlinked and not only_linked:
            explanation = (
                f"{source_type.replace('_', ' ').title()} '{source_title}' has no established relationship to this "
                "hypothesis. An investigator must decide whether it is supporting, contradicting, neutral, or contextual. "
                f"The assessment remains {previous} until that review is recorded."
            )
            records.append(create_impact_record(
                db, hypothesis, source_type, source_id, previous, previous, explanation,
                category="REQUIRES_INVESTIGATOR_REVIEW", trigger=trigger,
            ))
    return records


def list_impacts(
    db: Session,
    investigation_id: str | None = None,
    hypothesis_id: str | None = None,
    category: str | None = None,
    reviewed: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    query = select(HypothesisImpactRecord)
    if hypothesis_id:
        query = query.where(HypothesisImpactRecord.hypothesis_id == hypothesis_id)
    elif investigation_id:
        ids = select(Hypothesis.id).where(Hypothesis.investigation_id == investigation_id)
        query = query.where(HypothesisImpactRecord.hypothesis_id.in_(ids))
    if category:
        query = query.where(HypothesisImpactRecord.impact_category == category)
    if reviewed is not None:
        query = query.where(HypothesisImpactRecord.reviewed == reviewed)
    items = list(db.scalars(query.order_by(HypothesisImpactRecord.created_at.desc())).all())
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    start = (page - 1) * page_size
    from .serializers import impact_dict
    return {"items": [impact_dict(item) for item in items[start:start + page_size]], "total": len(items), "page": page, "page_size": page_size}


def review_impact(
    db: Session,
    hypothesis: Hypothesis,
    impact_id: str,
    reviewed_by: str,
    explanation: str,
) -> HypothesisImpactRecord:
    item = db.scalar(select(HypothesisImpactRecord).where(
        HypothesisImpactRecord.id == impact_id,
        HypothesisImpactRecord.hypothesis_id == hypothesis.id,
    ))
    if not item:
        raise HTTPException(status_code=404, detail="Impact record not found")
    if item.reviewed:
        raise HTTPException(status_code=409, detail="Impact record has already been reviewed")
    timestamp = now()
    item.reviewed = True
    item.requires_review = False
    item.reviewed_by = reviewed_by
    item.reviewed_at = timestamp
    item.review_note = (explanation or "").strip()
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=hypothesis.id,
        action="IMPACT_RECORD_REVIEWED",
        previous_value=f"{item.source_type}:{item.source_id}",
        new_value=item.impact_category,
        explanation=item.review_note or "Impact record reviewed by investigator.",
        performed_by=reviewed_by,
        created_at=timestamp,
    ))
    return item
