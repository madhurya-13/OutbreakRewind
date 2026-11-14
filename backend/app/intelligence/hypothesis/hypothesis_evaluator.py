"""Deterministic, reproducible qualitative hypothesis evaluation.

Rules (version 6.2)
-------------------
1. Withdrawn links are excluded from every count but retained in history.
2. A link counts as reviewed when its review status is REVIEWED or VERIFIED.
   Pending, disputed, and withdrawn links are never treated as reviewed support.
3. SIGNIFICANT_CONTRADICTIONS is selected when at least two linked
   contradictions remain unresolved, or when a reviewed contradiction combines
   with unresolved conflicts, or when reviewed contradictions outnumber reviewed
   supporting links and there are at least two of them.
4. MIXED_EVIDENCE is selected when both reviewed supporting and reviewed
   contradicting links exist and rule 3 does not apply.
5. SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE requires reviewed supporting
   evidence with no reviewed contradiction and at least one verified or strong
   reviewed supporting link.
6. PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE requires reviewed supporting
   evidence with no reviewed contradiction, but no verified/strong support.
7. LIMITED_SUPPORT means only reviewed neutral or contextual material exists.
8. INSUFFICIENT_INFORMATION means no link has been reviewed or verified.
9. NOT_YET_EVALUATED means no non-withdrawn link exists.

These thresholds govern review workflow labels, not scientific certainty. No
probability, percentage, or automatically selected "winning" hypothesis is
produced.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Hypothesis, HypothesisAssessment, HypothesisEvidenceLink
from .constants import (
    CLASSIFICATIONS,
    EVIDENCE_STRENGTHS,
    REVIEW_STATUSES,
    RULE_VERSION,
    SIGNIFICANT_CONTRADICTION_REVIEW_THRESHOLD,
    SOURCE_RELIABILITIES,
)
from .hypothesis_explainer import build_assessment_explanation, build_assessment_summary
from .serializers import json_dumps, json_loads, new_id, now
from .source_catalog import build_source_snapshot

REVIEWED_STATUSES = {"REVIEWED", "VERIFIED"}
RESOLVED_CONTRADICTION_STATUSES = {"RESOLVED", "DISMISSED"}


def _resolve_snapshot(db: Session, hypothesis: Hypothesis, link: HypothesisEvidenceLink) -> tuple[dict[str, Any], bool]:
    stored = json_loads(getattr(link, "source_snapshot", "{}"), {})
    current = build_source_snapshot(db, hypothesis.investigation_id, link.source_type, link.source_id)
    if current:
        return current, True
    if stored:
        stored["source_available"] = False
        return stored, False
    return {
        "source_type": link.source_type,
        "source_id": link.source_id,
        "title": getattr(link, "source_title", "") or link.source_id,
        "subtitle": "Source no longer available",
        "verification_status": "MISSING",
        "details": {},
        "source_available": False,
    }, False


def link_payload(db: Session, hypothesis: Hypothesis, link: HypothesisEvidenceLink) -> dict[str, Any]:
    snapshot, available = _resolve_snapshot(db, hypothesis, link)
    return {
        "link_id": link.id,
        "hypothesis_id": link.hypothesis_id,
        "source_type": link.source_type,
        "source_id": link.source_id,
        "source_title": getattr(link, "source_title", "") or snapshot.get("title") or link.source_id,
        "source_snapshot": snapshot,
        "source_available": available,
        "classification": link.classification,
        "explanation": link.explanation,
        "relevant_observations": link.relevant_observations,
        "evidence_strength": link.evidence_strength,
        "source_reliability": link.source_reliability,
        "strength_reason": link.strength_reason,
        "reliability_reason": link.reliability_reason,
        "review_status": link.review_status,
        "investigator_notes": link.investigator_notes,
        "linked_by": link.linked_by,
        "reviewed_by": getattr(link, "reviewed_by", ""),
        "reviewed_at": link.reviewed_at.isoformat() if getattr(link, "reviewed_at", None) else None,
        "created_at": link.created_at.isoformat(),
        "updated_at": link.updated_at.isoformat(),
    }


def active_links(db: Session, hypothesis_id: str) -> list[HypothesisEvidenceLink]:
    return list(db.scalars(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis_id,
        HypothesisEvidenceLink.review_status != "WITHDRAWN",
    ).order_by(HypothesisEvidenceLink.created_at.asc())).all())


def all_links(db: Session, hypothesis_id: str) -> list[HypothesisEvidenceLink]:
    return list(db.scalars(select(HypothesisEvidenceLink).where(
        HypothesisEvidenceLink.hypothesis_id == hypothesis_id
    ).order_by(HypothesisEvidenceLink.created_at.asc())).all())


def _empty_distribution(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _is_source_verified(snapshot: dict[str, Any]) -> bool:
    status = str(snapshot.get("verification_status") or "").upper()
    return status in {"VERIFIED", "CONFIRMED_CONFLICT", "VALIDATED"}


def _unresolved_contradictions(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for link in links:
        if link["source_type"] != "CONTRADICTION" or link["source_id"] in seen:
            continue
        status = str((link.get("source_snapshot") or {}).get("details", {}).get("status") or "").upper()
        if status not in RESOLVED_CONTRADICTION_STATUSES:
            seen.add(link["source_id"])
            result.append({
                "contradiction_id": link["source_id"],
                "title": link.get("source_title") or link["source_id"],
                "status": status or "UNKNOWN",
                "classification": link["classification"],
                "link_id": link["link_id"],
            })
    return result


def _decide_label(
    active: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    reviewed = [link for link in active if link["review_status"] in REVIEWED_STATUSES]
    supporting = [link for link in reviewed if link["classification"] == "SUPPORTING"]
    contradicting = [link for link in reviewed if link["classification"] == "CONTRADICTING"]
    neutral_contextual = [link for link in reviewed if link["classification"] in {"NEUTRAL", "CONTEXTUAL"}]
    strong_or_verified_support = [
        link for link in supporting
        if link["evidence_strength"] == "STRONG" or link["review_status"] == "VERIFIED"
    ]
    rules: list[dict[str, Any]] = []

    if not active:
        rules.append({"rule": "NO_ACTIVE_LINKS", "result": True, "because": "No non-withdrawn evidence link exists."})
        return "NOT_YET_EVALUATED", "no evidence link is available, so no evidence position can be described.", rules

    rules.append({
        "rule": "REVIEW_GATE",
        "result": bool(reviewed),
        "because": f"{len(reviewed)} of {len(active)} active link(s) are REVIEWED or VERIFIED.",
    })
    if not reviewed:
        return (
            "INSUFFICIENT_INFORMATION",
            "none of the linked sources has been reviewed or verified, so the material remains provisional.",
            rules,
        )

    significant = (
        len(unresolved) >= SIGNIFICANT_CONTRADICTION_REVIEW_THRESHOLD
        or (bool(unresolved) and bool(contradicting))
        or (len(contradicting) >= SIGNIFICANT_CONTRADICTION_REVIEW_THRESHOLD and len(contradicting) > len(supporting))
    )
    rules.append({
        "rule": "SIGNIFICANT_CONTRADICTIONS",
        "result": significant,
        "because": (
            f"{len(unresolved)} unresolved linked contradiction(s) and {len(contradicting)} reviewed "
            f"contradicting link(s) were compared with {len(supporting)} reviewed supporting link(s)."
        ),
    })
    if significant:
        return (
            "SIGNIFICANT_CONTRADICTIONS",
            "the reviewed and unresolved conflicts are substantial relative to the reviewed support.",
            rules,
        )

    mixed = bool(supporting) and bool(contradicting)
    rules.append({
        "rule": "MIXED_EVIDENCE",
        "result": mixed,
        "because": f"{len(supporting)} reviewed supporting and {len(contradicting)} reviewed contradicting link(s) are present.",
    })
    if mixed:
        return "MIXED_EVIDENCE", "reviewed evidence exists on both sides of the explanation.", rules

    substantial = bool(supporting) and not contradicting and bool(strong_or_verified_support)
    rules.append({
        "rule": "SUBSTANTIAL_SUPPORT",
        "result": substantial,
        "because": (
            f"{len(supporting)} reviewed supporting link(s) exist with no reviewed contradiction; "
            f"{len(strong_or_verified_support)} are strong or verified."
        ),
    })
    if substantial:
        return (
            "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE",
            "reviewed supporting evidence exists with no reviewed conflict and includes verified or strong support.",
            rules,
        )

    partial = bool(supporting) and not contradicting
    rules.append({
        "rule": "PARTIAL_SUPPORT",
        "result": partial,
        "because": f"{len(supporting)} reviewed supporting link(s) exist without strong or verified support.",
    })
    if partial:
        return "PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE", "reviewed support exists but is limited or unverified.", rules

    if contradicting:
        rules.append({"rule": "CONTRADICTION_WITHOUT_SUPPORT", "result": True, "because": "Only reviewed contradicting links exist."})
        return "SIGNIFICANT_CONTRADICTIONS", "reviewed contradicting evidence exists without reviewed support.", rules

    if neutral_contextual:
        rules.append({"rule": "CONTEXT_ONLY", "result": True, "because": "Only reviewed neutral or contextual links exist."})
        return "LIMITED_SUPPORT", "only neutral or contextual material has been reviewed; it does not directly support the explanation.", rules

    return "INSUFFICIENT_INFORMATION", "no reviewed link directly bears on the explanation.", rules


def evaluate_hypothesis(db: Session, hypothesis: Hypothesis, evaluated_by: str = "system") -> HypothesisAssessment:
    links = [link_payload(db, hypothesis, link) for link in active_links(db, hypothesis.id)]
    all_linked = all_links(db, hypothesis.id)
    withdrawn = sum(link.review_status == "WITHDRAWN" for link in all_linked)

    classification_counts = _empty_distribution(CLASSIFICATIONS)
    strength_counts = _empty_distribution(EVIDENCE_STRENGTHS)
    reliability_counts = _empty_distribution(SOURCE_RELIABILITIES)
    review_counts = _empty_distribution(REVIEW_STATUSES)
    for link in links:
        classification_counts[link["classification"]] = classification_counts.get(link["classification"], 0) + 1
        strength_counts[link["evidence_strength"]] = strength_counts.get(link["evidence_strength"], 0) + 1
        reliability_counts[link["source_reliability"]] = reliability_counts.get(link["source_reliability"], 0) + 1
        review_counts[link["review_status"]] = review_counts.get(link["review_status"], 0) + 1

    verified = sum(link["review_status"] == "VERIFIED" for link in links)
    reviewed = sum(link["review_status"] == "REVIEWED" for link in links)
    pending = sum(link["review_status"] == "PENDING_REVIEW" for link in links)
    disputed = sum(link["review_status"] == "DISPUTED" for link in links)
    missing_sources = [link for link in links if not link["source_available"]]
    unverified_sources = [
        link for link in links
        if link["review_status"] not in {"VERIFIED"}
        and not _is_source_verified(link.get("source_snapshot") or {})
    ]
    unresolved = _unresolved_contradictions(links)
    not_assessed_strength = sum(link["evidence_strength"] == "NOT_ASSESSED" for link in links)
    not_assessed_reliability = sum(link["source_reliability"] == "NOT_ASSESSED" for link in links)

    missing_information: list[str] = []
    if not links:
        missing_information.append("No evidence has been linked to this hypothesis.")
    if links and not (verified or reviewed):
        missing_information.append("No linked source has been reviewed or verified.")
    if pending:
        missing_information.append(f"{pending} linked source(s) are still pending investigator review.")
    if disputed:
        missing_information.append(f"{disputed} linked source(s) are disputed.")
    if missing_sources:
        missing_information.append(f"{len(missing_sources)} linked source(s) can no longer be found in the investigation.")
    if unresolved:
        missing_information.append(f"{len(unresolved)} linked contradiction(s) remain unresolved or under review.")
    if not_assessed_strength:
        missing_information.append(f"{not_assessed_strength} linked source(s) have no evidence-strength assessment.")
    if not_assessed_reliability:
        missing_information.append(f"{not_assessed_reliability} linked source(s) have no source-reliability assessment.")

    if not links or not (verified or reviewed) or missing_sources:
        missing_severity = "HIGH"
    elif pending or disputed or unresolved or not_assessed_strength or not_assessed_reliability:
        missing_severity = "MODERATE"
    else:
        missing_severity = "LOW"

    label, decision_reason, rules_applied = _decide_label(links, unresolved)
    explanation = build_assessment_explanation(
        hypothesis, label, decision_reason, {
            "supporting": classification_counts["SUPPORTING"],
            "contradicting": classification_counts["CONTRADICTING"],
            "neutral": classification_counts["NEUTRAL"],
            "contextual": classification_counts["CONTEXTUAL"],
            "verified": verified,
            "reviewed": reviewed,
            "pending": pending,
            "not_assessed_strength": not_assessed_strength,
            "not_assessed_reliability": not_assessed_reliability,
            "missing_sources": len(missing_sources),
            "unresolved_contradictions": len(unresolved),
        },
        links, missing_information, unresolved, unverified_sources, rules_applied, missing_severity,
    )

    counts_for_summary = {
        "supporting": classification_counts["SUPPORTING"],
        "contradicting": classification_counts["CONTRADICTING"],
        "neutral": classification_counts["NEUTRAL"],
        "contextual": classification_counts["CONTEXTUAL"],
        "verified": verified,
        "pending": pending,
        "unresolved_contradictions": len(unresolved),
    }
    details = {
        "rule_version": RULE_VERSION,
        "evaluated_by": evaluated_by,
        "counts": {
            **classification_counts,
            "verified": verified,
            "reviewed": reviewed,
            "pending_review": pending,
            "disputed": disputed,
            "withdrawn": withdrawn,
            "missing_sources": len(missing_sources),
            "unresolved_contradictions": len(unresolved),
            "total_linked": len(links),
        },
        "strength_distribution": strength_counts,
        "reliability_distribution": reliability_counts,
        "review_status_distribution": review_counts,
        "sources": links,
        "explanation": explanation,
        "missing_information_severity": missing_severity,
        "evaluation_rules": rules_applied,
        "supported_by": [link["link_id"] for link in links if link["classification"] == "SUPPORTING"],
        "contradicted_by": [link["link_id"] for link in links if link["classification"] == "CONTRADICTING"],
    }

    assessment = HypothesisAssessment(
        id=new_id("HAS"),
        hypothesis_id=hypothesis.id,
        assessment_label=label,
        assessment_summary=build_assessment_summary(label, counts_for_summary, missing_severity),
        supporting_count=classification_counts["SUPPORTING"],
        contradicting_count=classification_counts["CONTRADICTING"],
        neutral_count=classification_counts["NEUTRAL"],
        contextual_count=classification_counts["CONTEXTUAL"],
        verified_count=verified,
        pending_review_count=pending,
        strong_count=strength_counts["STRONG"],
        moderate_count=strength_counts["MODERATE"],
        limited_count=strength_counts["LIMITED"],
        unresolved_contradiction_count=len(unresolved),
        missing_information=json_dumps(missing_information),
        assessment_details=json_dumps(details),
        evaluation_rule_version=RULE_VERSION,
        evaluated_at=now(),
    )
    db.add(assessment)
    hypothesis.current_assessment = label
    hypothesis.updated_at = assessment.evaluated_at
    return assessment


def latest_assessment(db: Session, hypothesis_id: str) -> HypothesisAssessment | None:
    return db.scalar(select(HypothesisAssessment).where(
        HypothesisAssessment.hypothesis_id == hypothesis_id
    ).order_by(HypothesisAssessment.evaluated_at.desc(), HypothesisAssessment.id.desc()))


def assessment_history(db: Session, hypothesis_id: str) -> list[HypothesisAssessment]:
    return list(db.scalars(select(HypothesisAssessment).where(
        HypothesisAssessment.hypothesis_id == hypothesis_id
    ).order_by(HypothesisAssessment.evaluated_at.desc(), HypothesisAssessment.id.desc())).all())
