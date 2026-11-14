"""Hypothesis lifecycle management and investigation-level orchestration."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...models import (
    Hypothesis,
    HypothesisAssessment,
    HypothesisEvidenceLink,
    HypothesisImpactRecord,
    HypothesisNote,
    HypothesisReviewHistory,
)
from .constants import ASSESSMENT_LABELS, CATEGORIES, STATUSES
from .hypothesis_evaluator import evaluate_hypothesis, latest_assessment
from .hypothesis_versioning import hypothesis_snapshot, initial_version, record_version
from .serializers import (
    assessment_dict,
    hypothesis_dict,
    json_dumps,
    new_id,
    note_dict,
    now,
    review_dict,
)
from .validator import (
    clean_required,
    clean_string_list,
    ensure_unique_title,
    normalize_category,
)

INVESTIGATION_IDS = {"ORION-001", "ORION-002", "ORION-003"}


def require_investigation(investigation_id: str) -> str:
    if investigation_id not in INVESTIGATION_IDS:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation_id


def _list_value(value: Any) -> list[str]:
    return value if isinstance(value, list) else []


def create_hypothesis(db: Session, investigation_id: str, payload: dict[str, Any]) -> Hypothesis:
    require_investigation(investigation_id)
    title = clean_required(payload.get("title"), "Hypothesis title", minimum=3, maximum=180)
    description = clean_required(payload.get("description"), "Short description", minimum=10, maximum=5000)
    ensure_unique_title(db, investigation_id, title)
    category = normalize_category(payload.get("category"))
    actor = str(payload.get("created_by") or "investigator").strip()[:120] or "investigator"
    timestamp = now()
    item = Hypothesis(
        id=new_id("HYP"),
        investigation_id=investigation_id,
        title=title,
        category=category,
        description=description,
        detailed_explanation=str(payload.get("detailed_explanation") or "").strip()[:20000],
        assumptions=json_dumps(clean_string_list(payload.get("assumptions"), "assumptions")),
        predictions=json_dumps(clean_string_list(payload.get("predictions"), "expected observations")),
        limitations=json_dumps(clean_string_list(payload.get("limitations"), "limitations")),
        open_questions=json_dumps(clean_string_list(payload.get("open_questions"), "open questions")),
        status="DRAFT",
        current_assessment="NOT_YET_EVALUATED",
        current_version=1,
        created_by=actor,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(item)
    db.flush()
    initial_version(db, item, actor)
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=item.id,
        action="HYPOTHESIS_CREATED",
        previous_value="",
        new_value=item.title,
        explanation="Initial competing explanation created.",
        performed_by=actor,
        created_at=timestamp,
    ))
    initial_notes = str(payload.get("initial_notes") or "").strip()
    if initial_notes:
        db.add(HypothesisNote(
            id=new_id("HNOTE"),
            hypothesis_id=item.id,
            note=initial_notes[:10000],
            created_by=actor,
            created_at=timestamp,
            updated_at=timestamp,
        ))
    return item


def update_hypothesis(db: Session, hypothesis: Hypothesis, payload: dict[str, Any]) -> Hypothesis:
    fields = ("title", "description", "detailed_explanation", "assumptions", "predictions", "limitations", "open_questions")
    changes: dict[str, Any] = {}
    for field in fields:
        if field in payload and payload[field] is not None:
            changes[field] = payload[field]
    if "category" in payload and payload["category"] is not None:
        changes["category"] = normalize_category(payload["category"])
    if not changes:
        raise HTTPException(status_code=422, detail="No hypothesis fields were supplied")

    if "title" in changes:
        changes["title"] = clean_required(changes["title"], "Hypothesis title", minimum=3, maximum=180)
        ensure_unique_title(db, hypothesis.investigation_id, changes["title"], exclude_id=hypothesis.id)
    if "description" in changes:
        changes["description"] = clean_required(changes["description"], "Short description", minimum=10, maximum=5000)
    for field in ("assumptions", "predictions", "limitations", "open_questions"):
        if field in changes:
            changes[field] = clean_string_list(changes[field], field.replace("_", " "))

    actor = str(payload.get("updated_by") or "investigator")[:120]
    previous = hypothesis_snapshot(db, hypothesis)
    previous_values = {field: getattr(hypothesis, field) for field in changes}
    for field, value in changes.items():
        setattr(hypothesis, field, json_dumps(value) if isinstance(value, list) else value)
    hypothesis.updated_at = now()
    reason = str(payload.get("reason") or "").strip()
    record_version(
        db, hypothesis, actor,
        "Updated hypothesis details: " + ", ".join(sorted(changes.keys())),
        reason=reason,
        previous_data=previous,
    )
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=hypothesis.id,
        action="DETAILS_UPDATED",
        previous_value=json_dumps(previous_values),
        new_value=json_dumps({key: getattr(hypothesis, key) for key in changes}),
        explanation=reason or "Hypothesis details updated by investigator.",
        performed_by=actor,
        created_at=hypothesis.updated_at,
    ))
    return hypothesis


def update_status(db: Session, hypothesis: Hypothesis, status: str, explanation: str, actor: str) -> Hypothesis:
    if status not in STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported hypothesis status")
    if status == hypothesis.status:
        raise HTTPException(status_code=409, detail=f"Hypothesis is already {status}")
    previous = hypothesis_snapshot(db, hypothesis)
    previous_status = hypothesis.status
    hypothesis.status = status
    if status == "ARCHIVED":
        hypothesis.archived_at = now()
    elif hypothesis.archived_at is not None:
        hypothesis.archived_at = None
    hypothesis.updated_at = now()
    record_version(
        db, hypothesis, actor,
        f"Investigator changed status from {previous_status} to {status}.",
        reason=explanation,
        previous_data=previous,
    )
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=hypothesis.id,
        action="STATUS_CHANGED",
        previous_value=previous_status,
        new_value=status,
        explanation=(explanation or "Investigator status decision.")[:5000],
        performed_by=actor,
        created_at=hypothesis.updated_at,
    ))
    return hypothesis


def archive_hypothesis(db: Session, hypothesis: Hypothesis, actor: str = "investigator", reason: str = "") -> Hypothesis:
    if hypothesis.status == "ARCHIVED":
        raise HTTPException(status_code=409, detail="Hypothesis is already archived")
    previous = hypothesis_snapshot(db, hypothesis)
    previous_status = hypothesis.status
    hypothesis.status = "ARCHIVED"
    hypothesis.archived_at = now()
    hypothesis.updated_at = hypothesis.archived_at
    record_version(
        db, hypothesis, actor,
        "Hypothesis archived; all history and evidence links retained.",
        reason=reason or "Archived by investigator.",
        previous_data=previous,
    )
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"),
        hypothesis_id=hypothesis.id,
        action="ARCHIVED",
        previous_value=previous_status,
        new_value="ARCHIVED",
        explanation=reason or "Archived by investigator; records retained.",
        performed_by=actor,
        created_at=hypothesis.updated_at,
    ))
    return hypothesis


def _with_assessment(db: Session, item: Hypothesis) -> dict[str, Any]:
    result = hypothesis_dict(item)
    assessment = latest_assessment(db, item.id)
    result["assessment"] = assessment_dict(assessment) if assessment else None
    return result


def list_hypotheses(
    db: Session,
    investigation_id: str,
    status: str | None = None,
    category: str | None = None,
    assessment: str | None = None,
    search: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
    include_archived: bool = True,
) -> dict[str, Any]:
    require_investigation(investigation_id)
    query = select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)
    if status:
        query = query.where(Hypothesis.status == status)
    elif not include_archived:
        query = query.where(Hypothesis.status != "ARCHIVED")
    if category:
        query = query.where(Hypothesis.category == category)
    if assessment:
        query = query.where(Hypothesis.current_assessment == assessment)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(
            Hypothesis.title.ilike(term),
            Hypothesis.description.ilike(term),
            Hypothesis.detailed_explanation.ilike(term),
        ))
    sort_column = {
        "updated_at": Hypothesis.updated_at,
        "created_at": Hypothesis.created_at,
        "title": Hypothesis.title,
        "status": Hypothesis.status,
        "assessment": Hypothesis.current_assessment,
    }.get(sort, Hypothesis.updated_at)
    query = query.order_by(sort_column.desc() if order.lower() != "asc" else sort_column.asc())
    items = list(db.scalars(query).all())
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    return {
        "items": [_with_assessment(db, item) for item in items[start:start + page_size]],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }


def hypothesis_detail(db: Session, hypothesis: Hypothesis) -> dict[str, Any]:
    from .evidence_linker import list_links
    result = _with_assessment(db, hypothesis)
    result["latest_assessment"] = result.get("assessment")
    result["evidence"] = list_links(db, hypothesis)
    result["notes_count"] = db.scalar(select(func.count()).select_from(HypothesisNote).where(
        HypothesisNote.hypothesis_id == hypothesis.id
    )) or 0
    result["pending_impact_count"] = db.scalar(select(func.count()).select_from(HypothesisImpactRecord).where(
        HypothesisImpactRecord.hypothesis_id == hypothesis.id,
        HypothesisImpactRecord.requires_review.is_(True),
    )) or 0
    return result


def investigation_summary(db: Session, investigation_id: str) -> dict[str, Any]:
    require_investigation(investigation_id)
    hypotheses = list(db.scalars(select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)).all())
    active = [item for item in hypotheses if item.status != "ARCHIVED"]
    ids = [item.id for item in hypotheses]
    pending_impacts = 0
    if ids:
        pending_impacts = db.scalar(select(func.count()).select_from(HypothesisImpactRecord).where(
            HypothesisImpactRecord.hypothesis_id.in_(ids),
            HypothesisImpactRecord.requires_review.is_(True),
        )) or 0
    pending_links = 0
    if ids:
        pending_links = db.scalar(select(func.count()).select_from(HypothesisEvidenceLink).where(
            HypothesisEvidenceLink.hypothesis_id.in_(ids),
            HypothesisEvidenceLink.review_status == "PENDING_REVIEW",
        )) or 0
    supporting = []
    for item in active:
        assessment = latest_assessment(db, item.id)
        if (assessment and assessment.supporting_count > 0) or item.current_assessment in {
            "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE",
            "PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE",
        }:
            supporting.append(item)
    recent_cutoff = now().timestamp() - 7 * 24 * 3600
    recently_updated = [
        item for item in active
        if item.updated_at and item.updated_at.timestamp() >= recent_cutoff
    ]
    return {
        "investigation_id": investigation_id,
        "total_hypotheses": len(hypotheses),
        "active_hypotheses": len(active),
        "under_investigation": sum(item.status == "UNDER_INVESTIGATION" for item in active),
        "with_supporting_evidence": len(supporting),
        "significant_contradictions": sum(item.current_assessment == "SIGNIFICANT_CONTRADICTIONS" for item in active),
        "mixed_evidence": sum(item.current_assessment == "MIXED_EVIDENCE" for item in active),
        "insufficient_information": sum(item.current_assessment == "INSUFFICIENT_INFORMATION" for item in active),
        "not_yet_evaluated": sum(item.current_assessment == "NOT_YET_EVALUATED" for item in active),
        "archived": sum(item.status == "ARCHIVED" for item in hypotheses),
        "requiring_review": pending_impacts + pending_links,
        "pending_impact_records": pending_impacts,
        "pending_evidence_links": pending_links,
        "recently_updated": len(recently_updated),
        "recent_hypotheses": [
            {"hypothesis_id": item.id, "title": item.title, "status": item.status,
             "assessment": item.current_assessment, "updated_at": item.updated_at.isoformat()}
            for item in sorted(active, key=lambda value: value.updated_at, reverse=True)[:5]
        ],
        "categories": sorted(CATEGORIES),
        "statuses": list(STATUSES),
        "assessment_labels": list(ASSESSMENT_LABELS),
    }


def evaluate_investigation_hypotheses(db: Session, investigation_id: str, evaluated_by: str = "investigator") -> dict[str, Any]:
    """Central orchestration service required by the milestone."""
    require_investigation(investigation_id)
    hypotheses = list(db.scalars(select(Hypothesis).where(
        Hypothesis.investigation_id == investigation_id,
        Hypothesis.status != "ARCHIVED",
    )).all())
    items = []
    for hypothesis in hypotheses:
        previous = hypothesis.current_assessment
        assessment = evaluate_hypothesis(db, hypothesis, evaluated_by=evaluated_by)
        items.append({
            "hypothesis_id": hypothesis.id,
            "title": hypothesis.title,
            "previous_assessment": previous,
            "assessment": assessment_dict(assessment),
        })
    return {
        "investigation_id": investigation_id,
        "items": items,
        "evaluated_count": len(items),
        "rule_version": "6.2",
        "disclaimer": "Assessments describe available reviewed evidence only. They do not establish causation or select a correct hypothesis.",
    }


def hypothesis_history(db: Session, hypothesis: Hypothesis) -> dict[str, Any]:
    from ...models import HypothesisVersion
    versions = list(db.scalars(select(HypothesisVersion).where(
        HypothesisVersion.hypothesis_id == hypothesis.id
    ).order_by(HypothesisVersion.version_number.desc())).all())
    reviews = list(db.scalars(select(HypothesisReviewHistory).where(
        HypothesisReviewHistory.hypothesis_id == hypothesis.id
    ).order_by(HypothesisReviewHistory.created_at.desc())).all())
    assessments = list(db.scalars(select(HypothesisAssessment).where(
        HypothesisAssessment.hypothesis_id == hypothesis.id
    ).order_by(HypothesisAssessment.evaluated_at.desc())).all())
    from .serializers import version_dict
    return {
        "versions": [version_dict(item) for item in versions],
        "reviews": [review_dict(item) for item in reviews],
        "assessments": [assessment_dict(item) for item in assessments],
    }


def add_note(db: Session, hypothesis: Hypothesis, note: str, created_by: str = "investigator") -> HypothesisNote:
    text = clean_required(note, "Note", minimum=2, maximum=10000)
    timestamp = now()
    item = HypothesisNote(
        id=new_id("HNOTE"), hypothesis_id=hypothesis.id, note=text,
        created_by=(created_by or "investigator")[:120], created_at=timestamp, updated_at=timestamp,
    )
    db.add(item)
    db.add(HypothesisReviewHistory(
        id=new_id("HREV"), hypothesis_id=hypothesis.id, action="NOTE_ADDED",
        previous_value="", new_value=text[:1000], explanation="Investigator note added.",
        performed_by=created_by, created_at=timestamp,
    ))
    return item


def list_notes(db: Session, hypothesis: Hypothesis) -> list[dict[str, Any]]:
    return [note_dict(item) for item in db.scalars(select(HypothesisNote).where(
        HypothesisNote.hypothesis_id == hypothesis.id
    ).order_by(HypothesisNote.created_at.desc())).all()]
