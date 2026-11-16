"""Deterministic comparison of two reconstructed investigation states."""
from __future__ import annotations

from typing import Any

from .utils import content_hash, iso

CATEGORY_LABELS = {
    "evidence": "evidence records",
    "timeline": "timeline events",
    "network": "network relationships",
    "contradictions": "contradictions",
    "hypotheses": "hypotheses",
}

STATUS_FIELDS = {"status", "verification_status", "review_status", "temporal_status"}
CLASSIFICATION_FIELDS = {"classification", "relationship_classification", "category", "severity", "current_assessment"}


def _change_timestamp(state: dict[str, Any], entity_id: str) -> str:
    for event in reversed(state.get("recent_changes") or []):
        if event.get("entity_id") == entity_id:
            return event.get("recorded_at") or state.get("as_of")
    return state.get("as_of")


def _difference(kind: str, entity_type: str, entity_id: str, previous: Any, current: Any, timestamp: str, explanation: str, source_reference: Any = None) -> dict[str, Any]:
    return {
        "entity_type": entity_type, "entity_id": entity_id, "category": kind,
        "difference_type": "MODIFIED", "previous_value": previous, "current_value": current,
        "change_timestamp": timestamp, "explanation": explanation,
        "source_reference": source_reference or {},
    }


def _diff_collection(
    kind: str, entity_type: str, previous: list[dict[str, Any]], current: list[dict[str, Any]],
    state_b: dict[str, Any], label_field: str = "title",
) -> list[dict[str, Any]]:
    previous_by = {str(item.get("evidence_id") or item.get("event_id") or item.get("relationship_id") or item.get("contradiction_id") or item.get("hypothesis_id") or item.get("id")): item for item in previous}
    current_by = {str(item.get("evidence_id") or item.get("event_id") or item.get("relationship_id") or item.get("contradiction_id") or item.get("hypothesis_id") or item.get("id")): item for item in current}
    result: list[dict[str, Any]] = []
    for entity_id, item in current_by.items():
        if entity_id not in previous_by:
            result.append({
                "entity_type": entity_type, "entity_id": entity_id, "category": kind,
                "difference_type": "ADDED", "previous_value": None, "current_value": item,
                "change_timestamp": _change_timestamp(state_b, entity_id),
                "explanation": f"{label_field.replace('_', ' ').title()} '{item.get(label_field) or entity_id}' was recorded after the first cutoff.",
                "source_reference": item.get("sources") or item.get("source_reference") or {},
            })
    for entity_id, item in previous_by.items():
        if entity_id not in current_by:
            result.append({
                "entity_type": entity_type, "entity_id": entity_id, "category": kind,
                "difference_type": "REMOVED", "previous_value": item, "current_value": None,
                "change_timestamp": state_b.get("as_of"),
                "explanation": f"{label_field.replace('_', ' ').title()} '{item.get(label_field) or entity_id}' was not present at the later cutoff.",
                "source_reference": item.get("sources") or item.get("source_reference") or {},
            })
            continue
        before = previous_by[entity_id]
        changed_fields = []
        for field in sorted(set(before) | set(item)):
            if field in {"sources", "evidence", "comparisons", "reviews", "assessment", "evidence_links", "notes", "review_history", "audit_history", "recent_changes"}:
                continue
            if before.get(field) != item.get(field):
                changed_fields.append(field)
        if not changed_fields:
            continue
        if any(field in STATUS_FIELDS for field in changed_fields):
            difference_type = "STATUS_CHANGED"
            if item.get("status") == "RESOLVED":
                difference_type = "RESOLVED"
            elif item.get("status") == "REOPENED":
                difference_type = "REOPENED"
            elif item.get("verification_status") == "VERIFIED":
                difference_type = "VERIFIED"
            elif item.get("verification_status") == "REJECTED" or item.get("status") == "DISMISSED":
                difference_type = "DISPUTED"
        elif any(field in CLASSIFICATION_FIELDS for field in changed_fields):
            difference_type = "RECLASSIFIED"
        else:
            difference_type = "MODIFIED"
        previous_values = {field: before.get(field) for field in changed_fields}
        current_values = {field: item.get(field) for field in changed_fields}
        result.append({
            "entity_type": entity_type, "entity_id": entity_id, "category": kind,
            "difference_type": difference_type, "previous_value": previous_values,
            "current_value": current_values, "change_timestamp": _change_timestamp(state_b, entity_id),
            "explanation": f"Changed fields: {', '.join(changed_fields)}.",
            "source_reference": item.get("sources") or item.get("source_reference") or {},
        })
    return result


def _hypothesis_diff(previous: list[dict[str, Any]], current: list[dict[str, Any]], state_b: dict[str, Any]) -> list[dict[str, Any]]:
    result = _diff_collection("hypotheses", "HYPOTHESIS", previous, current, state_b, "title")
    previous_by = {item["hypothesis_id"]: item for item in previous}
    for item in current:
        before = previous_by.get(item["hypothesis_id"])
        if not before:
            continue
        before_assessment = (before.get("assessment") or {}).get("assessment_label")
        after_assessment = (item.get("assessment") or {}).get("assessment_label")
        if before_assessment != after_assessment:
            result.append(_difference(
                "hypotheses", "HYPOTHESIS_ASSESSMENT", item["hypothesis_id"],
                {"assessment": before_assessment}, {"assessment": after_assessment},
                _change_timestamp(state_b, item["hypothesis_id"]),
                f"Assessment changed from {before_assessment or 'not evaluated'} to {after_assessment or 'not evaluated'}.",
                {"hypothesis_id": item["hypothesis_id"]},
            ))
        before_links = {link.get("link_id"): link for link in before.get("evidence_links") or []}
        after_links = {link.get("link_id"): link for link in item.get("evidence_links") or []}
        for link_id, link in after_links.items():
            old = before_links.get(link_id)
            if not old:
                result.append(_difference("hypotheses", "HYPOTHESIS_EVIDENCE_LINK", link_id, None, link, _change_timestamp(state_b, item["hypothesis_id"]), "Evidence link was added to the hypothesis.", {"hypothesis_id": item["hypothesis_id"], "link_id": link_id}))
            elif old.get("classification") != link.get("classification"):
                result.append({
                    **_difference("hypotheses", "HYPOTHESIS_EVIDENCE_LINK", link_id, {"classification": old.get("classification")}, {"classification": link.get("classification")}, _change_timestamp(state_b, item["hypothesis_id"]), "Evidence classification changed.", {"hypothesis_id": item["hypothesis_id"]}),
                    "difference_type": "RECLASSIFIED",
                })
    return result


def compare_investigation_states(
    investigation_id: str,
    state_a: dict[str, Any],
    state_b: dict[str, Any],
) -> dict[str, Any]:
    if state_a.get("investigation_id") != investigation_id or state_b.get("investigation_id") != investigation_id:
        raise ValueError("Both states must belong to the selected investigation")
    differences: list[dict[str, Any]] = []
    differences += _diff_collection("evidence", "EVIDENCE_DOCUMENT", state_a.get("evidence") or [], state_b.get("evidence") or [], state_b, "filename")
    differences += _diff_collection("timeline", "RECONSTRUCTED_EVENT", (state_a.get("timeline") or {}).get("events") or [], (state_b.get("timeline") or {}).get("events") or [], state_b, "event_description")
    differences += _diff_collection("network", "GRAPH_RELATIONSHIP", (state_a.get("network") or {}).get("relationships") or [], (state_b.get("network") or {}).get("relationships") or [], state_b, "relationship_id")
    differences += _diff_collection("contradictions", "CONTRADICTION", state_a.get("contradictions") or [], state_b.get("contradictions") or [], state_b, "title")
    differences += _hypothesis_diff(state_a.get("hypotheses") or [], state_b.get("hypotheses") or [], state_b)
    differences.sort(key=lambda item: (item.get("change_timestamp") or "", item.get("category") or "", item.get("entity_id") or ""))
    counts = {kind: sum(item["category"] == kind for item in differences) for kind in CATEGORY_LABELS}
    change_counts = {value: sum(item["difference_type"] == value for item in differences) for value in ("ADDED", "REMOVED", "MODIFIED", "STATUS_CHANGED", "RECLASSIFIED", "VERIFIED", "DISPUTED", "RESOLVED", "REOPENED", "UNKNOWN")}
    summary = (
        f"Between {state_a.get('as_of')} and {state_b.get('as_of')}, "
        f"{change_counts['ADDED']} items were added, {change_counts['REMOVED']} removed, "
        f"{change_counts['MODIFIED'] + change_counts['RECLASSIFIED']} modified or reclassified, "
        f"and {change_counts['STATUS_CHANGED'] + change_counts['VERIFIED'] + change_counts['DISPUTED'] + change_counts['RESOLVED'] + change_counts['REOPENED']} changed status."
    )
    return {
        "investigation_id": investigation_id,
        "state_a": {"as_of": state_a.get("as_of"), "summary": state_a.get("summary")},
        "state_b": {"as_of": state_b.get("as_of"), "summary": state_b.get("summary")},
        "differences": differences,
        "by_category": counts,
        "by_change_type": change_counts,
        "summary": summary,
        "comparison_hash": content_hash([state_a.get("as_of"), state_b.get("as_of"), differences]),
        "disclaimer": "Differences describe recorded information only. They do not establish transmission, causation, or scientific correctness.",
    }