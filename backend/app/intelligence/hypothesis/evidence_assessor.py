"""Evidence strength suggestions and assessment explanation helpers.

Evidence strength asks how directly and meaningfully a source bears on one
particular hypothesis. It is not a property of the file, and it is never
inferred from the number of records.
"""
from typing import Any

from .constants import STRENGTH_DESCRIPTIONS


def suggest_strength(snapshot: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    if not snapshot:
        return "INSUFFICIENT", "The source could not be resolved, so it cannot inform the hypothesis.", ["Source missing."]

    source_type = snapshot.get("source_type", "")
    details = snapshot.get("details") or {}
    considerations: list[str] = []

    if source_type == "INVESTIGATOR_NOTE":
        return (
            "LIMITED",
            "A manual note can add context but is not independently corroborated evidence.",
            ["Working observation only.", "Requires corroboration by a source record."],
        )

    if source_type == "EXTRACTED_RECORD":
        identifiers = sum(bool(details.get(key)) for key in ("person_id", "event_date", "location_id", "location", "contact_person_id"))
        verification = str(details.get("verification_status") or "").upper()
        if identifiers >= 2:
            considerations.append(f"The record contains {identifiers} explicit identifying fields.")
        else:
            considerations.append("The record contains few explicit identifying fields.")
        considerations.append(f"Record verification status is {verification or 'unknown'}.")
        if identifiers >= 2 and verification == "VERIFIED":
            return "STRONG", "The record is verified and contains explicit identifiers relevant to the hypothesis.", considerations
        if identifiers >= 1:
            return "MODERATE", "The record contains some explicit detail but is incomplete or unverified.", considerations
        return "LIMITED", "The record is narrative or incomplete and cannot be tied precisely to the hypothesis.", considerations

    if source_type == "EVIDENCE_DOCUMENT":
        record_count = int(details.get("record_count") or 0)
        status = str(details.get("status") or "").upper()
        considerations.append(f"The document contains {record_count} extracted record(s).")
        considerations.append(f"Document processing status is {status or 'unknown'}.")
        if record_count > 0 and status == "VALIDATED":
            return "MODERATE", "The document is validated and contains extracted records, but document-level evidence is indirect.", considerations
        return "LIMITED", "The document has limited extraction or validation support.", considerations

    if source_type == "RECONSTRUCTED_EVENT":
        precision = str(details.get("date_precision") or "").upper()
        verification = str(details.get("verification_status") or "").upper()
        considerations.append(f"Date precision is {precision or 'not recorded'}.")
        considerations.append(f"Event verification status is {verification or 'unknown'}.")
        if precision == "DAY" and verification == "VERIFIED":
            return "STRONG", "The event has an exact date and was verified by an investigator.", considerations
        if precision in {"DAY", "RANGE", "MONTH"}:
            return "MODERATE", "The reconstructed event is dated but its precision or verification is limited.", considerations
        return "LIMITED", "The event date is unresolved or the event is only weakly reconstructed.", considerations

    if source_type == "GRAPH_RELATIONSHIP":
        classification = str(details.get("classification") or "").upper()
        verification = str(snapshot.get("verification_status") or "").upper()
        considerations.append(f"Relationship classification is {classification or 'UNKNOWN'}.")
        considerations.append(f"Relationship verification status is {verification or 'unknown'}.")
        if classification == "EXPLICIT" and verification == "VERIFIED":
            return "STRONG", "The relationship is explicitly recorded and verified.", considerations
        if classification == "EXPLICIT":
            return "MODERATE", "The relationship is explicitly recorded but not yet verified.", considerations
        return "LIMITED", "The relationship is inferred or possible and should not be treated as a recorded contact.", considerations

    if source_type == "CONTRADICTION":
        comparisons = details.get("comparison_count") or 0
        status = str(details.get("status") or "").upper()
        considerations.append(f"The conflict contains {comparisons} field comparison(s).")
        considerations.append(f"Contradiction review status is {status or 'unknown'}.")
        if status == "CONFIRMED_CONFLICT" and comparisons:
            return "STRONG", "The conflict was confirmed by an investigator and contains explicit field comparisons.", considerations
        if comparisons:
            return "MODERATE", "The conflict contains field-level comparisons but remains under review.", considerations
        return "LIMITED", "The conflict lacks enough comparable detail to inform the hypothesis.", considerations

    if source_type == "TEMPORAL_FINDING":
        considerations.append("The finding is derived from stored event records.")
        return "LIMITED", "A temporal finding is a review prompt rather than direct evidence for the hypothesis.", considerations

    return "INSUFFICIENT", "The source type cannot be assessed with the available metadata.", considerations


def default_strength_reason(category: str, snapshot: dict[str, Any] | None) -> str:
    if category not in STRENGTH_DESCRIPTIONS or category == "NOT_ASSESSED":
        return "No evidence-strength assessment has been recorded yet."
    return f"Investigator assessed evidence strength as {category}: {STRENGTH_DESCRIPTIONS[category]}"


def assessment_reasoning(strength: str, reliability: str, classification: str) -> list[str]:
    """Human-readable separation of the three independent assessments."""
    return [
        f"Relationship to hypothesis: {classification}.",
        f"Evidence strength: {strength} ({STRENGTH_DESCRIPTIONS.get(strength, 'not assessed')}).",
        f"Source reliability: {reliability}. Reliability is judged independently of whether the source supports the hypothesis.",
    ]
