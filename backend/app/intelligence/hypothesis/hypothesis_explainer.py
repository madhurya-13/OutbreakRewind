"""Deterministic explanation generation for assessments and impact records.


The explainer only narrates facts already stored on hypothesis links and source
snapshots. It never invents a source, a fact, or a classification, and it never
changes an investigator decision. No external model is required.
"""
import json
import re
from typing import Any

from .constants import (
    ASSESSMENT_DESCRIPTIONS,
    ASSESSMENT_DISCLAIMER,
    CLASSIFICATION_DESCRIPTIONS,
    STRENGTH_DESCRIPTIONS,
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "that", "this", "it", "as", "by", "at", "from", "be",
    "may", "might", "could", "would", "should", "has", "have", "had", "not",
}

STRENGTH_ORDER = {"STRONG": 0, "MODERATE": 1, "LIMITED": 2, "INSUFFICIENT": 3, "NOT_ASSESSED": 4}
RELIABILITY_ORDER = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "UNKNOWN": 3, "NOT_ASSESSED": 4}


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(word) > 2 and word not in STOPWORDS}


def assumption_coverage(assumptions: list[str], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage = []
    for assumption in assumptions or []:
        words = _tokens(assumption)
        best = None
        best_score = 0.0
        for link in links:
            if link["review_status"] == "WITHDRAWN":
                continue
            text = " ".join(str(link.get(key) or "") for key in ("explanation", "relevant_observations", "investigator_notes"))
            text += " " + str((link.get("source_snapshot") or {}).get("title") or "")
            overlap = words & _tokens(text)
            score = len(overlap) / max(len(words), 1)
            if score > best_score:
                best_score = score
                best = link
        if best and best_score >= 0.2:
            coverage.append({
                "assumption": assumption,
                "status": "ADDRESSED_IN_LINK",
                "link_id": best["link_id"],
                "reason": f"Linked source '{best.get('source_title') or best['source_id']}' is described in terms related to this assumption.",
            })
        else:
            coverage.append({
                "assumption": assumption,
                "status": "NOT_EXPLICITLY_ADDRESSED",
                "link_id": None,
                "reason": "No linked evidence explanation explicitly addresses this assumption; investigator review remains required.",
            })
    return coverage


def build_assessment_explanation(
    hypothesis: Any,
    label: str,
    decision_reason: str,
    counts: dict[str, int],
    links: list[dict[str, Any]],
    missing_information: list[str],
    unresolved_contradictions: list[dict[str, Any]],
    unverified_sources: list[dict[str, Any]],
    rules_applied: list[dict[str, Any]],
    missing_severity: str,
) -> dict[str, Any]:
    active = [link for link in links if link["review_status"] != "WITHDRAWN"]
    supporting = sorted(
        [link for link in active if link["classification"] == "SUPPORTING"],
        key=lambda link: (STRENGTH_ORDER.get(link["evidence_strength"], 9), 0 if link["review_status"] == "VERIFIED" else 1),
    )
    conflicting = sorted(
        [link for link in active if link["classification"] == "CONTRADICTING"],
        key=lambda link: (STRENGTH_ORDER.get(link["evidence_strength"], 9), 0 if link["review_status"] == "VERIFIED" else 1),
    )
    neutral = [link for link in active if link["classification"] == "NEUTRAL"]
    contextual = [link for link in active if link["classification"] == "CONTEXTUAL"]

    def describe(link: dict[str, Any]) -> dict[str, Any]:
        return {
            "link_id": link["link_id"],
            "source_type": link["source_type"],
            "source_id": link["source_id"],
            "source_title": link.get("source_title") or link["source_id"],
            "classification": link["classification"],
            "evidence_strength": link["evidence_strength"],
            "source_reliability": link["source_reliability"],
            "review_status": link["review_status"],
            "explanation": link["explanation"],
        }

    next_review = []
    if counts["pending"]:
        next_review.append(f"Review {counts['pending']} linked source(s) still marked PENDING_REVIEW.")
    if counts["not_assessed_strength"]:
        next_review.append(f"Assess evidence strength for {counts['not_assessed_strength']} linked source(s).")
    if counts["not_assessed_reliability"]:
        next_review.append(f"Assess source reliability for {counts['not_assessed_reliability']} linked source(s).")
    if unresolved_contradictions:
        next_review.append(f"Resolve or dismiss {len(unresolved_contradictions)} linked contradiction(s) in the Contradiction Center.")
    if counts["missing_sources"]:
        next_review.append(f"Re-check {counts['missing_sources']} linked source(s) that are no longer available.")
    if unverified_sources:
        next_review.append(f"Inspect provenance for {len(unverified_sources)} source(s) that are not verified.")
    if not active:
        next_review.append("Link at least one existing investigation record before evaluating this hypothesis.")
    if not next_review:
        next_review.append("Continue investigator review; no outstanding workflow item was detected by the rule set.")

    raw_assumptions = getattr(hypothesis, "assumptions", None)
    if isinstance(raw_assumptions, str):
        try:
            raw_assumptions = json.loads(raw_assumptions)
        except (TypeError, ValueError):
            raw_assumptions = []
    assumptions = raw_assumptions if isinstance(raw_assumptions, list) else []
    coverage = assumption_coverage(assumptions, links)
    raw_questions = getattr(hypothesis, "open_questions", None)
    if isinstance(raw_questions, str):
        try:
            raw_questions = json.loads(raw_questions)
        except (TypeError, ValueError):
            raw_questions = []
    open_questions = [str(value) for value in (raw_questions or [])]

    why_parts = [
        f"The stored evidence contains {counts['supporting']} supporting, {counts['contradicting']} contradicting, "
        f"{counts['neutral']} neutral, and {counts['contextual']} contextual linked source(s).",
        f"{counts['verified']} source link(s) are verified and {counts['reviewed']} more are reviewed.",
        f"The rule set selected {label} because {decision_reason}",
    ]
    if unresolved_contradictions:
        why_parts.append(f"{len(unresolved_contradictions)} linked contradiction(s) remain unresolved or under review.")
    if counts["pending"]:
        why_parts.append(f"{counts['pending']} source link(s) remain pending review and are treated as provisional.")

    return {
        "rule_version": "6.2",
        "assessment_label": label,
        "assessment_meaning": ASSESSMENT_DESCRIPTIONS.get(label, ""),
        "why": " ".join(why_parts),
        "decision_reason": decision_reason,
        "rules_applied": rules_applied,
        "influential_sources": [describe(link) for link in supporting[:5]],
        "conflicting_sources": [describe(link) for link in conflicting[:5]],
        "neutral_sources": [describe(link) for link in neutral[:5]],
        "contextual_sources": [describe(link) for link in contextual[:5]],
        "unverified_sources": [describe(link) for link in unverified_sources[:10]],
        "unresolved_contradictions": unresolved_contradictions[:10],
        "unverified_assumptions": [item for item in coverage if item["status"] != "ADDRESSED_IN_LINK"],
        "assumption_coverage": coverage,
        "missing_information": missing_information,
        "missing_information_severity": missing_severity,
        "open_questions": open_questions,
        "recommended_next_review": next_review,
        "strength_definitions": STRENGTH_DESCRIPTIONS,
        "classification_definitions": CLASSIFICATION_DESCRIPTIONS,
        "disclaimer": ASSESSMENT_DISCLAIMER,
    }


def build_assessment_summary(label: str, counts: dict[str, int], missing_severity: str) -> str:
    if label == "NOT_YET_EVALUATED":
        return (
            "Not yet evaluated: no linked evidence is available for this hypothesis. "
            "Link traceable investigation records, then run an evaluation."
        )
    text = (
        f"{label.replace('_', ' ').title()}. {counts['supporting']} supporting, "
        f"{counts['contradicting']} contradicting, {counts['neutral']} neutral, and "
        f"{counts['contextual']} contextual sources are linked. {counts['verified']} link(s) are verified; "
        f"{counts['pending']} remain pending review."
    )
    if counts["unresolved_contradictions"]:
        text += f" {counts['unresolved_contradictions']} linked contradiction(s) remain unresolved."
    text += f" Missing-information indicator: {missing_severity.lower()}. {ASSESSMENT_DISCLAIMER}"
    return text


def assumption_tokens(text: str) -> set[str]:
    return _tokens(text)
