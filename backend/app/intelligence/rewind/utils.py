"""Shared deterministic helpers for historical reconstruction."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any


KNOWN_INVESTIGATIONS = {
    "ORION-001": "Project Orion",
    "ORION-002": "North Cascades Sentinel",
    "ORION-003": "East Ridge Cluster",
}

INVESTIGATION_META = {
    "ORION-001": {"investigation_name": "Project Orion", "description": "A fictional respiratory outbreak investigation used exclusively for demonstrating the platform.", "outbreak_category": "Respiratory", "status": "Active", "total_cases": 124},
    "ORION-002": {"investigation_name": "North Cascades Sentinel", "description": "Synthetic sentinel investigation for a regional signal.", "outbreak_category": "Respiratory", "status": "Review", "total_cases": 38},
    "ORION-003": {"investigation_name": "East Ridge Cluster", "description": "Synthetic cluster reconstruction for training workflows.", "outbreak_category": "Unknown", "status": "Archived", "total_cases": 17},
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even for timezone=True columns."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def parse_timestamp(value: str | datetime | None, *, field: str = "timestamp") -> datetime:
    if isinstance(value, datetime):
        return aware(value) or utcnow()
    if not value or not str(value).strip():
        raise ValueError(f"{field} is required")
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return aware(datetime.fromisoformat(raw)) or utcnow()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def dumps(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def content_hash(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def within(value: datetime | None, cutoff: datetime) -> bool:
    moment = aware(value)
    return moment is not None and moment <= cutoff


def new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def model_dict(item: Any) -> dict[str, Any]:
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    return json_safe(result)