"""Validation helpers for hypothesis identifiers, categories, and text fields."""
import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Hypothesis
from .constants import CATEGORIES, SOURCE_TYPES, STATUSES

CATEGORY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def normalize_category(value: str | None) -> str:
    category = (value or "UNKNOWN_OR_UNCLASSIFIED").strip().upper().replace(" ", "_").replace("-", "_")
    if category in CATEGORIES or CATEGORY_PATTERN.fullmatch(category):
        return category
    raise HTTPException(
        status_code=422,
        detail="Category must be a documented category or an uppercase custom category such as LOCAL_WATER_SOURCE.",
    )


def require_status(value: str) -> str:
    if value not in STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported hypothesis status")
    return value


def require_source_type(value: str) -> str:
    if value not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported evidence source type")
    return value


def clean_required(value: str | None, field: str, minimum: int = 1, maximum: int = 5000) -> str:
    text = (value or "").strip()
    if len(text) < minimum:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    if len(text) > maximum:
        raise HTTPException(status_code=422, detail=f"{field} must be {maximum} characters or fewer")
    return text


def clean_string_list(values: list[str] | None, field: str) -> list[str]:
    result = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        if len(text) > 1000:
            raise HTTPException(status_code=422, detail=f"Each {field} entry must be 1000 characters or fewer")
        result.append(text)
    return result[:100]


def ensure_unique_title(db: Session, investigation_id: str, title: str, exclude_id: str | None = None) -> None:
    query = select(Hypothesis.id).where(
        Hypothesis.investigation_id == investigation_id,
        func.lower(Hypothesis.title) == title.lower(),
    )
    if exclude_id:
        query = query.where(Hypothesis.id != exclude_id)
    if db.scalar(query):
        raise HTTPException(
            status_code=409,
            detail="A hypothesis with this title already exists in the investigation. Choose a distinct title.",
        )


def require_hypothesis(db: Session, hypothesis_id: str) -> Hypothesis:
    item = db.get(Hypothesis, hypothesis_id)
    if not item:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return item


def require_hypothesis_in_investigation(db: Session, investigation_id: str, hypothesis_id: str) -> Hypothesis:
    item = require_hypothesis(db, hypothesis_id)
    if item.investigation_id != investigation_id:
        # Do not reveal that a hypothesis exists in another investigation.
        raise HTTPException(status_code=404, detail="Hypothesis not found in this investigation")
    return item
