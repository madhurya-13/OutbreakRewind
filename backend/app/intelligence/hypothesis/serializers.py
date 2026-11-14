"""Serialization helpers shared by the hypothesis services and API routes."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ...models import (
    Hypothesis,
    HypothesisAssessment,
    HypothesisEvidenceLink,
    HypothesisImpactRecord,
    HypothesisNote,
    HypothesisReviewHistory,
    HypothesisVersion,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def json_loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, default=str)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def hypothesis_dict(item: Hypothesis) -> dict[str, Any]:
    return {
        "id": item.id,
        "hypothesis_id": item.id,
        "investigation_id": item.investigation_id,
        "title": item.title,
        "category": item.category,
        "description": item.description,
        "detailed_explanation": item.detailed_explanation,
        "assumptions": json_loads(item.assumptions, []),
        "predictions": json_loads(item.predictions, []),
        "limitations": json_loads(item.limitations, []),
        "open_questions": json_loads(item.open_questions, []),
        "status": item.status,
        "current_assessment": item.current_assessment,
        "current_version": item.current_version,
        "created_by": item.created_by,
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
        "archived_at": iso(getattr(item, "archived_at", None)),
    }


def link_dict(item: HypothesisEvidenceLink, include_snapshot: bool = True) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["link_id"] = item.id
    result["created_at"] = iso(item.created_at)
    result["updated_at"] = iso(item.updated_at)
    result["reviewed_at"] = iso(getattr(item, "reviewed_at", None))
    result["source_title"] = getattr(item, "source_title", "") or ""
    if include_snapshot:
        result["source_snapshot"] = json_loads(getattr(item, "source_snapshot", "{}"), {})
    else:
        result.pop("source_snapshot", None)
    return result


def assessment_dict(item: HypothesisAssessment) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["assessment_id"] = item.id
    result["missing_information"] = json_loads(item.missing_information, [])
    result["assessment_details"] = json_loads(item.assessment_details, {})
    result["evaluated_at"] = iso(item.evaluated_at)
    return result


def impact_dict(item: HypothesisImpactRecord) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["impact_id"] = item.id
    result["created_at"] = iso(item.created_at)
    result["reviewed_at"] = iso(getattr(item, "reviewed_at", None))
    return result


def version_dict(item: HypothesisVersion, include_previous: bool = True) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["created_at"] = iso(item.created_at)
    result["snapshot_data"] = json_loads(item.snapshot_data, {})
    if include_previous:
        result["previous_data"] = json_loads(getattr(item, "previous_data", "{}"), {})
    else:
        result.pop("previous_data", None)
    return result


def note_dict(item: HypothesisNote) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["created_at"] = iso(item.created_at)
    result["updated_at"] = iso(item.updated_at)
    return result


def review_dict(item: HypothesisReviewHistory) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    result["created_at"] = iso(item.created_at)
    return result
