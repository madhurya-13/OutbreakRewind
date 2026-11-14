"""Backward-compatible facade for the modular Hypothesis Intelligence Engine.

New code should import from the individual modules or from the package
``app.intelligence.hypothesis``. This module keeps the original Milestone 6
imports working while the API migrates to the package exports.
"""
from sqlalchemy.orm import Session

from .constants import RULE_VERSION
from .evidence_impact_analyzer import (
    analyze_source_change,
    create_impact_record,
    list_impacts,
    review_impact,
)
from .evidence_linker import link_evidence, list_links, update_link, withdraw_link
from .hypothesis_comparator import compare_hypotheses
from .hypothesis_evaluator import (
    assessment_history,
    evaluate_hypothesis,
    latest_assessment,
    link_payload,
)
from .hypothesis_manager import (
    add_note,
    archive_hypothesis,
    create_hypothesis,
    evaluate_investigation_hypotheses,
    hypothesis_detail,
    hypothesis_history,
    investigation_summary,
    list_hypotheses,
    list_notes,
    update_hypothesis,
    update_status,
)
from .hypothesis_versioning import record_version
from .serializers import (
    assessment_dict,
    hypothesis_dict,
    impact_dict,
    json_loads,
    link_dict,
    new_id,
    note_dict,
    now,
    review_dict,
    version_dict,
)
from .source_catalog import build_source_catalog, build_source_snapshot, source_exists


def _source_exists(db: Session, hypothesis, source_type: str, source_id: str) -> bool:
    return source_exists(db, hypothesis.investigation_id, source_type, source_id)


def create_version(db: Session, hypothesis, changed_by: str, description: str, reason: str = "") -> None:
    """Legacy helper retained for callers that create a version explicitly."""
    record_version(db, hypothesis, changed_by, description, reason=reason)


__all__ = [
    "RULE_VERSION", "analyze_source_change", "assessment_dict", "create_impact_record",
    "create_version", "evaluate_hypothesis", "evaluate_investigation_hypotheses",
    "hypothesis_detail", "hypothesis_dict", "hypothesis_history", "impact_dict",
    "investigation_summary", "json_loads", "latest_assessment", "link_dict", "link_evidence",
    "list_hypotheses", "list_links", "new_id", "now", "source_exists", "_source_exists",
    "build_source_catalog", "compare_hypotheses", "add_note", "list_notes",
    "update_hypothesis", "update_status", "archive_hypothesis", "withdraw_link",
    "update_link", "review_impact", "list_impacts", "record_version", "version_dict",
    "note_dict", "review_dict", "link_payload", "assessment_history",
]
