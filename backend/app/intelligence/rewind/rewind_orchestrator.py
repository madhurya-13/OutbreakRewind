"""Central orchestration facade for the Investigation Rewind engine."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .historical_reconstructor import (coverage_for_investigation,
                                       reconstruct_investigation_as_of)
from .investigation_comparator import compare_investigation_states
from .snapshot_manager import create_snapshot


def reconstruct_investigation_at(investigation_id: str, as_of_timestamp: str | datetime, db: Session) -> dict[str, Any]:
    return reconstruct_investigation_as_of(investigation_id, as_of_timestamp, db)


def compare_investigation_timestamps(investigation_id: str, timestamp_a: str | datetime, timestamp_b: str | datetime, db: Session) -> dict[str, Any]:
    state_a = reconstruct_investigation_as_of(investigation_id, timestamp_a, db)
    state_b = reconstruct_investigation_as_of(investigation_id, timestamp_b, db)
    return compare_investigation_states(investigation_id, state_a, state_b)


def snapshot_investigation(investigation_id: str, db: Session, **kwargs: Any):
    return create_snapshot(db, investigation_id, **kwargs)


def investigation_coverage(investigation_id: str, db: Session, as_of_timestamp: str | datetime | None = None) -> dict[str, Any]:
    return coverage_for_investigation(investigation_id, db, as_of_timestamp)