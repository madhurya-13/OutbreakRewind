"""Explainable source reliability suggestions.

Reliability describes the quality and traceability of a source, not whether the
source supports a particular hypothesis. Suggestions are informational only;
the investigator's explicit selection is stored on every evidence link.
"""
from typing import Any

from .constants import RELIABILITY_DESCRIPTIONS


def _value(snapshot: dict[str, Any], key: str, default: Any = "") -> Any:
    details = snapshot.get("details") or {}
    return details.get(key, default)


def suggest_reliability(snapshot: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    """Return (category, reason, considerations).

    The suggestion never silently becomes the stored assessment. It is displayed
    to the investigator in the linking interface with its reasoning.
    """
    if not snapshot:
        return "UNKNOWN", "No source metadata is available to assess reliability.", ["Source could not be resolved."]

    source_type = snapshot.get("source_type", "")
    verification = str(snapshot.get("verification_status") or "").upper()
    details = snapshot.get("details") or {}
    considerations: list[str] = []

    if source_type == "INVESTIGATOR_NOTE":
        return (
            "UNKNOWN",
            "An investigator note is a working observation, not a documentary source; its reliability depends on corroboration.",
            ["Manually entered note.", "No independent source reference is attached."],
        )

    if verification in {"FAILED", "REJECTED", "DISPUTED", "NEEDS_REVIEW"}:
        considerations.append(f"Source status is {verification}.")
        considerations.append("Unresolved verification or conflict limits reliability.")
        return "LOW", "The source is unverified, rejected, disputed, or awaiting review.", considerations

    has_reference = bool(snapshot.get("original_reference"))
    if has_reference:
        considerations.append("A traceable original record reference is preserved.")
    else:
        considerations.append("No traceable original reference was found.")

    if source_type == "EVIDENCE_DOCUMENT":
        status = str(details.get("status") or verification).upper()
        if status == "VALIDATED" and has_reference:
            considerations.append("The uploaded document passed extraction validation and has a checksum.")
            return "MODERATE", "The document is validated and traceable, but uploaded documents are not automatically verified.", considerations
        considerations.append(f"Document processing status is {status or 'unknown'}.")
        return "LOW", "The document has processing, extraction, or validation limitations.", considerations

    if source_type == "EXTRACTED_RECORD":
        record_verification = str(details.get("verification_status") or verification).upper()
        if record_verification == "VERIFIED" and has_reference:
            considerations.append("The extracted record was manually verified.")
            return "HIGH", "The extracted record was manually verified and retains its evidence and row/page reference.", considerations
        if record_verification in {"REJECTED", "DISPUTED"}:
            considerations.append("The extracted record was rejected or disputed.")
            return "LOW", "The extracted record is rejected or disputed.", considerations
        considerations.append("The extracted record is still pending manual verification.")
        return "MODERATE", "The extracted record is traceable but has not been manually verified.", considerations

    if source_type == "RECONSTRUCTED_EVENT":
        event_verification = str(details.get("verification_status") or verification).upper()
        precision = str(details.get("date_precision") or "").upper()
        if precision in {"UNKNOWN", "AMBIGUOUS"}:
            considerations.append("The event date is unresolved or ambiguous.")
        else:
            considerations.append(f"Event date precision is {precision or 'not recorded'}.")
        if event_verification == "VERIFIED":
            considerations.append("The reconstructed event was verified by an investigator.")
            return "HIGH", "The reconstructed event is verified and retains its source links.", considerations
        considerations.append("The reconstructed event is not yet verified.")
        return "MODERATE", "The reconstructed event is traceable but not yet verified.", considerations

    if source_type == "GRAPH_RELATIONSHIP":
        classification = str(details.get("classification") or "").upper()
        considerations.append(f"The relationship is classified {classification or 'UNKNOWN'}.")
        if verification == "VERIFIED" and classification == "EXPLICIT":
            considerations.append("The explicit relationship was verified.")
            return "HIGH", "The relationship is explicit and has been verified.", considerations
        if classification in {"INFERRED", "POSSIBLE"}:
            considerations.append("The relationship is derived rather than explicitly recorded.")
            return "LOW", "The relationship is inferred or possible, not an explicitly recorded contact.", considerations
        considerations.append("The relationship has not been verified.")
        return "MODERATE", "The explicit relationship is traceable but not yet verified.", considerations

    if source_type == "CONTRADICTION":
        status = str(details.get("status") or "").upper()
        considerations.append(f"Contradiction review status is {status or 'unknown'}.")
        if status in {"DETECTED", "UNDER_REVIEW"}:
            return "MODERATE", "The conflict is a machine-detected review candidate and is not itself a verified fact.", considerations
        return "LOW", "The conflict remains unresolved or is disputed as a source of evidence.", considerations

    if source_type == "TEMPORAL_FINDING":
        considerations.append("Temporal findings are derived review prompts, not primary records.")
        return "MODERATE", "The temporal finding is derived from stored records and is traceable to them.", considerations

    return "UNKNOWN", "Source reliability cannot be determined from stored metadata.", considerations or ["No metadata available."]


def default_reliability_reason(category: str, snapshot: dict[str, Any] | None) -> str:
    code = category if category in RELIABILITY_DESCRIPTIONS else "NOT_ASSESSED"
    if code == "NOT_ASSESSED":
        return "No reliability assessment has been recorded yet."
    return f"Investigator assessed source reliability as {code}: {RELIABILITY_DESCRIPTIONS[code]}"
