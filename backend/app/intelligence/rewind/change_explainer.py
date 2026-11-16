"""Rule-based explanations for recorded investigation changes."""
from __future__ import annotations

from typing import Any


def explain_event(event: dict[str, Any]) -> str:
    type_ = str(event.get("event_type") or "CHANGE")
    entity = str(event.get("entity_id") or "record")
    actor = event.get("actor_id") or "the system"
    when = event.get("recorded_at") or "the recorded time"
    descriptions = {
        "EVIDENCE_UPLOADED": f"{actor} uploaded evidence {entity}, making its extracted information available from {when}.",
        "EVIDENCE_RECORD_VERIFIED": f"{actor} verified extracted record {entity}; the verification is visible from {when} onward.",
        "EVIDENCE_RECORD_DISPUTED": f"{actor} disputed extracted record {entity}, adding a review flag without deleting the source.",
        "TIMELINE_RECONSTRUCTED": f"{actor} reconstructed the timeline, creating a new recorded timeline state at {when}.",
        "EVENT_DATE_REVISED": f"{actor} revised the date of reconstructed event {entity}; the earlier value remains in audit history.",
        "EVENT_VERIFIED": f"{actor} verified reconstructed event {entity} at {when}.",
        "NETWORK_RECONSTRUCTED": f"{actor} rebuilt the case network from the evidence and timeline available at {when}.",
        "RELATIONSHIP_REVIEWED": f"{actor} reviewed relationship {entity}, changing its investigator verification state.",
        "CONTRADICTION_DETECTED": f"The contradiction engine identified finding {entity}; it requires investigator review and is not an automatic judgment.",
        "CONTRADICTION_RESOLVED": f"{actor} resolved contradiction {entity} with a recorded review note.",
        "CONTRADICTION_REOPENED": f"{actor} reopened contradiction {entity} after new recorded information changed the review context.",
        "HYPOTHESIS_CREATED": f"{actor} created competing hypothesis {entity}.",
        "HYPOTHESIS_STATUS_CHANGED": f"{actor} recorded an investigator-controlled status decision for hypothesis {entity}.",
        "HYPOTHESIS_EVALUATED": f"The deterministic rule engine reassessed hypothesis {entity} against the evidence linked at {when}.",
        "HYPOTHESIS_EVIDENCE_LINKED": f"{actor} linked a traceable source to hypothesis {entity} and recorded the classification rationale.",
        "HYPOTHESIS_EVIDENCE_RECLASSIFIED": f"{actor} reclassified a linked source for hypothesis {entity}; the prior link assessment remains in history.",
        "HYPOTHESIS_EVIDENCE_WITHDRAWN": f"{actor} withdrew an evidence link from hypothesis {entity} while retaining the source and audit trail.",
        "SNAPSHOT_CREATED": f"{actor} captured immutable snapshot {entity}.",
    }
    return descriptions.get(type_, f"{actor} recorded {type_.replace('_', ' ').lower()} for {entity} at {when}.")


def explain_assessment_change(previous: dict[str, Any] | None, current: dict[str, Any] | None, newly_linked: list[dict[str, Any]] | None = None) -> str:
    before = (previous or {}).get("assessment_label") or "not evaluated"
    after = (current or {}).get("assessment_label") or "not evaluated"
    supporting = (current or {}).get("supporting_count", 0)
    contradicting = (current or {}).get("contradicting_count", 0)
    unresolved = (current or {}).get("unresolved_contradiction_count", 0)
    linked = len(newly_linked or [])
    parts = [f"The recorded assessment changed from {before} to {after}."]
    if linked:
        parts.append(f"{linked} newly recorded evidence link(s) contributed to the reassessment.")
    parts.append(f"The stored assessment counts {supporting} supporting and {contradicting} contradicting reviewed links, with {unresolved} unresolved linked contradiction(s).")
    parts.append("This describes the available reviewed evidence only; it does not prove that the hypothesis is scientifically correct.")
    return " ".join(parts)


def explain_comparison(differences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "human_explanation": item.get("explanation") or f"{item.get('entity_type')} {item.get('entity_id')} changed."} for item in differences]