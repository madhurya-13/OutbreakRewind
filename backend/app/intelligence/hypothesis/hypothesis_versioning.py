"""Append-only hypothesis version history."""
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Hypothesis, HypothesisEvidenceLink, HypothesisVersion
from .serializers import hypothesis_dict, json_dumps, json_loads, new_id, now


def hypothesis_snapshot(db: Session, hypothesis: Hypothesis) -> dict[str, Any]:
    links = db.scalars(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis.id
    ).order_by(HypothesisEvidenceLink.created_at.asc())).all()
    return {
        **hypothesis_dict(hypothesis),
        "evidence_links": [{
            "link_id": link.id,
            "source_type": link.source_type,
            "source_id": link.source_id,
            "source_title": getattr(link, "source_title", ""),
            "classification": link.classification,
            "evidence_strength": link.evidence_strength,
            "source_reliability": link.source_reliability,
            "review_status": link.review_status,
            "explanation": link.explanation,
        } for link in links],
    }


def initial_version(db: Session, hypothesis: Hypothesis, actor: str, description: str = "Initial hypothesis created") -> HypothesisVersion:
    return record_version(db, hypothesis, actor, description, increment=False)


def record_version(
    db: Session,
    hypothesis: Hypothesis,
    actor: str,
    description: str,
    reason: str = "",
    previous_data: dict[str, Any] | None = None,
    increment: bool = True,
) -> HypothesisVersion:
    """Store the resulting state (and, where supplied, the previous state).

    Versions are never updated or deleted. Evidence link changes are included in
    the snapshot so classification, strength, and reliability changes remain
    inspectable.
    """
    if increment:
        hypothesis.current_version = int(hypothesis.current_version or 1) + 1
    item = HypothesisVersion(
        id=new_id("HVER"),
        hypothesis_id=hypothesis.id,
        version_number=hypothesis.current_version,
        snapshot_data=json_dumps(hypothesis_snapshot(db, hypothesis)),
        previous_data=json_dumps(previous_data or {}),
        change_description=(description or "").strip()[:1000],
        reason=(reason or "").strip()[:2000],
        changed_by=actor or "investigator",
        created_at=now(),
    )
    db.add(item)
    return item


def version_detail(db: Session, hypothesis_id: str, version_number: int) -> HypothesisVersion | None:
    return db.scalar(select(HypothesisVersion).where(
        HypothesisVersion.hypothesis_id == hypothesis_id,
        HypothesisVersion.version_number == version_number,
    ))
