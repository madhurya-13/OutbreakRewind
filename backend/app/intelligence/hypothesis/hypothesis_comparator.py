"""Side-by-side comparison of competing hypotheses from the same investigation."""
from collections import defaultdict
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Hypothesis, HypothesisEvidenceLink, HypothesisImpactRecord, HypothesisNote
from .constants import CLASSIFICATIONS, DISCLAIMER, EVIDENCE_STRENGTHS, REVIEW_STATUSES, SOURCE_RELIABILITIES
from .hypothesis_evaluator import active_links, latest_assessment, link_payload
from .serializers import assessment_dict, hypothesis_dict
from .source_catalog import build_source_snapshot
from .validator import require_hypothesis_in_investigation


def _counts(links: list[dict[str, Any]], key: str, values: tuple[str, ...]) -> dict[str, int]:
    return {value: sum(link[key] == value for link in links) for value in values}


def _cell(value: Any, display: str | None = None) -> dict[str, Any]:
    return {"value": value, "display": display if display is not None else str(value)}


def compare_hypotheses(db: Session, investigation_id: str, hypothesis_ids: list[str]) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(hypothesis_ids))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=422, detail="Select at least two hypotheses to compare")
    if len(unique_ids) > 6:
        raise HTTPException(status_code=422, detail="Compare at most six hypotheses at a time")

    hypotheses = []
    for hypothesis_id in unique_ids:
        hypotheses.append(require_hypothesis_in_investigation(db, investigation_id, hypothesis_id))

    rows: list[dict[str, Any]] = []
    source_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    recent_impacts: dict[str, int] = {}
    for hypothesis in hypotheses:
        links = [link_payload(db, hypothesis, link) for link in active_links(db, hypothesis.id)]
        assessment = latest_assessment(db, hypothesis.id)
        assessment_payload = assessment_dict(assessment) if assessment else None
        details = (assessment_payload or {}).get("assessment_details") or {}
        classification_counts = _counts(links, "classification", CLASSIFICATIONS)
        strength_counts = _counts(links, "evidence_strength", EVIDENCE_STRENGTHS)
        reliability_counts = _counts(links, "source_reliability", SOURCE_RELIABILITIES)
        review_counts = _counts(links, "review_status", REVIEW_STATUSES)
        unresolved = (details.get("counts") or {}).get("unresolved_contradictions", 0)
        missing = (assessment_payload or {}).get("missing_information") or []
        notes = list(db.scalars(select(HypothesisNote).where(
            HypothesisNote.hypothesis_id == hypothesis.id
        ).order_by(HypothesisNote.created_at.desc())).all())
        impacts = list(db.scalars(select(HypothesisImpactRecord).where(
            HypothesisImpactRecord.hypothesis_id == hypothesis.id
        )).all())
        recent_impacts[hypothesis.id] = sum(1 for item in impacts if item.requires_review)
        for link in links:
            source_map[(link["source_type"], link["source_id"])].append(hypothesis.title)
        rows.append({
            "hypothesis": hypothesis_dict(hypothesis),
            "assessment": assessment_payload,
            "evidence_counts": {
                "total": len(links),
                **classification_counts,
                "withdrawn": sum(1 for link in db.scalars(select(HypothesisEvidenceLink).where(
                    HypothesisEvidenceLink.hypothesis_id == hypothesis.id
                )).all() if link.review_status == "WITHDRAWN"),
            },
            "strength_distribution": strength_counts,
            "reliability_distribution": reliability_counts,
            "review_status_distribution": review_counts,
            "verified_count": review_counts["VERIFIED"],
            "pending_review_count": review_counts["PENDING_REVIEW"],
            "unresolved_contradiction_count": unresolved,
            "missing_information": missing,
            "open_questions": hypothesis_dict(hypothesis)["open_questions"],
            "assumptions": hypothesis_dict(hypothesis)["assumptions"],
            "notes": [{"note": item.note, "created_by": item.created_by, "created_at": item.created_at.isoformat()} for item in notes[:3]],
            "pending_impact_count": recent_impacts[hypothesis.id],
            "links": links,
        })

    titles = [row["hypothesis"]["title"] for row in rows]
    assessment_labels = [row["hypothesis"]["current_assessment"] for row in rows]

    def row(key: str, label: str, values: list[Any], displays: list[str] | None = None) -> dict[str, Any]:
        cells = []
        for index, value in enumerate(values):
            display = displays[index] if displays else str(value)
            cells.append(_cell(value, display))
        return {"key": key, "label": label, "cells": cells}

    supporting = [row["evidence_counts"]["SUPPORTING"] for row in rows]
    contradicting = [row["evidence_counts"]["CONTRADICTING"] for row in rows]
    neutral = [row["evidence_counts"]["NEUTRAL"] for row in rows]
    contextual = [row["evidence_counts"]["CONTEXTUAL"] for row in rows]
    strong = [row["strength_distribution"]["STRONG"] for row in rows]
    moderate = [row["strength_distribution"]["MODERATE"] for row in rows]
    limited = [row["strength_distribution"]["LIMITED"] for row in rows]
    high = [row["reliability_distribution"]["HIGH"] for row in rows]
    mod_rel = [row["reliability_distribution"]["MODERATE"] for row in rows]
    low = [row["reliability_distribution"]["LOW"] for row in rows]
    unresolved = [row["unresolved_contradiction_count"] for row in rows]
    missing = [len(row["missing_information"]) for row in rows]
    missing_severity = [
        ((row["assessment"] or {}).get("assessment_details") or {}).get("missing_information_severity", "HIGH")
        for row in rows
    ]

    matrix = [
        row("description", "Hypothesis description", [row["hypothesis"]["description"] for row in rows]),
        row("assumptions", "Main assumptions", [row["hypothesis"]["assumptions"] for row in rows],
            ["; ".join(row["hypothesis"]["assumptions"]) or "None recorded" for row in rows]),
        row("supporting", "Supporting evidence", supporting),
        row("contradicting", "Contradicting evidence", contradicting),
        row("neutral", "Neutral evidence", neutral),
        row("contextual", "Contextual evidence", contextual),
        row("strength", "Strong / moderate / limited", [
            f"{strong[i]} / {moderate[i]} / {limited[i]}" for i in range(len(rows))
        ]),
        row("reliability", "High / moderate / low reliability", [
            f"{high[i]} / {mod_rel[i]} / {low[i]}" for i in range(len(rows))
        ]),
        row("unresolved", "Unresolved contradictions", unresolved),
        row("missing", "Missing information", missing, [
            f"{missing[i]} item(s) · {missing_severity[i].title()}" for i in range(len(rows))
        ]),
        row("verified", "Verified source links", [row["verified_count"] for row in rows]),
        row("pending", "Pending review", [row["pending_review_count"] for row in rows]),
        row("open_questions", "Open questions", [len(row["open_questions"]) for row in rows],
            ["; ".join(row["open_questions"]) or "None recorded" for row in rows]),
        row("assessment", "Current assessment", assessment_labels, [
            label.replace("_", " ").title() for label in assessment_labels
        ]),
        row("status", "Investigator status", [row["hypothesis"]["status"] for row in rows],
            [row["hypothesis"]["status"].replace("_", " ").title() for row in rows]),
        row("updated", "Last updated", [row["hypothesis"]["updated_at"] for row in rows]),
        row("notes", "Investigator notes", [len(row["notes"]) for row in rows],
            [row["notes"][0]["note"][:180] if row["notes"] else "None recorded" for row in rows]),
    ]

    insights: list[str] = []
    for (source_type, source_id), linked_titles in source_map.items():
        unique_titles = list(dict.fromkeys(linked_titles))
        if len(unique_titles) > 1:
            title = source_id
            snapshot = build_source_snapshot(db, investigation_id, source_type, source_id)
            if snapshot:
                title = snapshot.get("title") or source_id
            insights.append(
                f"{' and '.join(unique_titles)} rely on the same underlying source ({source_type.replace('_', ' ').lower()}: {title}). "
                "This is not independent confirmation."
            )
    if len(set(assessment_labels)) == 1:
        insights.append(
            "All selected hypotheses currently share the same qualitative assessment. "
            "Available evidence does not sufficiently distinguish the competing explanations."
        )
    for index, row_data in enumerate(rows):
        if row_data["unresolved_contradiction_count"]:
            insights.append(
                f"{titles[index]} has {row_data['unresolved_contradiction_count']} unresolved contradiction(s) that require investigator review."
            )
        if row_data["verified_count"] and not row_data["pending_review_count"]:
            insights.append(f"{titles[index]} relies only on verified source links; provenance is comparatively complete.")
        if row_data["pending_review_count"]:
            insights.append(
                f"{titles[index]} has {row_data['pending_review_count']} link(s) pending review; its assessment remains provisional."
            )
        if row_data["pending_impact_count"]:
            insights.append(
                f"{titles[index]} has {row_data['pending_impact_count']} impact record(s) awaiting investigator review."
            )

    all_assumptions = [set(value.strip().lower() for value in row["assumptions"]) for row in rows]
    common = set.intersection(*all_assumptions) if all_assumptions and all(all_assumptions) else set()
    for assumption in list(common)[:3]:
        insights.append(
            f"The assumption '{assumption}' is shared by every selected hypothesis and is not independently established by the comparison."
        )

    if not any(row["evidence_counts"]["total"] for row in rows):
        insights.append("None of the selected hypotheses has linked evidence; counts alone cannot distinguish them.")
    if not insights:
        insights.append("No shared-source or conflict pattern was detected; continue documenting explicit evidence links.")

    return {
        "investigation_id": investigation_id,
        "hypothesis_ids": unique_ids,
        "hypotheses": rows,
        "comparison_matrix": matrix,
        "insights": insights,
        "disclaimer": DISCLAIMER,
        "explanation": DISCLAIMER,
        "rule_version": "6.2",
    }
