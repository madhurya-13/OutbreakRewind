"""Hypothesis Intelligence Engine (Milestone 6)."""
from .constants import ASSESSMENT_LABELS, CATEGORIES, CLASSIFICATIONS, STATUSES
from .evidence_impact_analyzer import analyze_source_change, create_impact_record, list_impacts, review_impact
from .evidence_linker import link_evidence, list_links, update_link, withdraw_link
from .hypothesis_comparator import compare_hypotheses
from .hypothesis_evaluator import assessment_history, evaluate_hypothesis, latest_assessment
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
from .serializers import (
    assessment_dict,
    hypothesis_dict,
    impact_dict,
    link_dict,
    note_dict,
    version_dict,
)
from .source_catalog import build_source_catalog, build_source_snapshot, source_exists

__all__ = [
    "assessment_dict", "hypothesis_dict", "impact_dict", "link_dict", "note_dict", "version_dict",
    "ASSESSMENT_LABELS", "CATEGORIES", "CLASSIFICATIONS", "STATUSES",
    "analyze_source_change", "create_impact_record", "list_impacts", "review_impact",
    "link_evidence", "list_links", "update_link", "withdraw_link",
    "compare_hypotheses", "assessment_history", "evaluate_hypothesis", "latest_assessment",
    "add_note", "archive_hypothesis", "create_hypothesis", "evaluate_investigation_hypotheses",
    "hypothesis_detail", "hypothesis_history", "investigation_summary", "list_hypotheses",
    "list_notes", "update_hypothesis", "update_status",
    "build_source_catalog", "build_source_snapshot", "source_exists",
]
