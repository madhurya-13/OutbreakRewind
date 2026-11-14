"""Central definitions for the Hypothesis Intelligence Engine.

The labels in this module are deliberately qualitative. Nothing here is a
probability, a diagnosis, or an automatically established conclusion.
"""

RULE_VERSION = "6.2"

STATUSES = (
    "DRAFT",
    "UNDER_INVESTIGATION",
    "SUPPORTED_BY_AVAILABLE_EVIDENCE",
    "CONTRADICTED_BY_AVAILABLE_EVIDENCE",
    "INCONCLUSIVE",
    "ARCHIVED",
)

CATEGORIES = (
    "COMMON_SOURCE_EXPOSURE",
    "PERSON_TO_PERSON_CONTACT",
    "SHARED_LOCATION_EXPOSURE",
    "MULTIPLE_INDEPENDENT_SOURCES",
    "ENVIRONMENTAL_EXPOSURE",
    "REPORTING_OR_DATA_ERROR",
    "UNKNOWN_OR_UNCLASSIFIED",
)

CLASSIFICATIONS = ("SUPPORTING", "CONTRADICTING", "NEUTRAL", "CONTEXTUAL")

REVIEW_STATUSES = ("PENDING_REVIEW", "REVIEWED", "VERIFIED", "DISPUTED", "WITHDRAWN")

EVIDENCE_STRENGTHS = ("STRONG", "MODERATE", "LIMITED", "INSUFFICIENT", "NOT_ASSESSED")

SOURCE_RELIABILITIES = ("HIGH", "MODERATE", "LOW", "UNKNOWN", "NOT_ASSESSED")

ASSESSMENT_LABELS = (
    "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE",
    "PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE",
    "MIXED_EVIDENCE",
    "LIMITED_SUPPORT",
    "SIGNIFICANT_CONTRADICTIONS",
    "INSUFFICIENT_INFORMATION",
    "NOT_YET_EVALUATED",
)

IMPACT_CATEGORIES = (
    "POTENTIALLY_SUPPORTS",
    "POTENTIALLY_CONTRADICTS",
    "ADDS_CONTEXT",
    "NO_CLEAR_IMPACT",
    "REQUIRES_INVESTIGATOR_REVIEW",
)

SOURCE_TYPES = (
    "EVIDENCE_DOCUMENT",
    "EXTRACTED_RECORD",
    "RECONSTRUCTED_EVENT",
    "GRAPH_RELATIONSHIP",
    "CONTRADICTION",
    "TEMPORAL_FINDING",
    "INVESTIGATOR_NOTE",
)

# Review-workflow thresholds. These decide which qualitative label is shown to
# an investigator so that the same stored evidence always yields the same
# label. They are not a measure of scientific certainty and must not be
# presented as probabilities.
SIGNIFICANT_CONTRADICTION_REVIEW_THRESHOLD = 2
MIN_REVIEWED_FOR_ASSESSMENT = 1

DISCLAIMER = (
    "Current evidence comparison is exploratory and does not establish causation "
    "or determine the correct hypothesis."
)

ASSESSMENT_DISCLAIMER = (
    "This is a qualitative assessment of the available, reviewed records. It is "
    "not a medical conclusion, a confirmed transmission chain, or a finding of causation."
)

STATUS_DESCRIPTIONS = {
    "DRAFT": "Being written; not yet an active line of inquiry.",
    "UNDER_INVESTIGATION": "Actively being tested against available evidence.",
    "SUPPORTED_BY_AVAILABLE_EVIDENCE": "The investigator judges that available evidence supports the explanation.",
    "CONTRADICTED_BY_AVAILABLE_EVIDENCE": "The investigator judges that available evidence conflicts with the explanation.",
    "INCONCLUSIVE": "Available evidence does not currently distinguish this explanation.",
    "ARCHIVED": "Retained for audit; no longer part of the active comparison.",
}

CLASSIFICATION_DESCRIPTIONS = {
    "SUPPORTING": "Consistent with the hypothesis or a reason to consider it more plausible.",
    "CONTRADICTING": "Conflicts with an assumption, prediction, or proposed explanation.",
    "NEUTRAL": "Does not meaningfully favor or oppose the hypothesis.",
    "CONTEXTUAL": "Background or investigation context that does not directly evaluate the hypothesis.",
}

STRENGTH_DESCRIPTIONS = {
    "STRONG": "Directly and precisely addresses the hypothesis with traceable detail.",
    "MODERATE": "Addresses the hypothesis but with some missing or indirect detail.",
    "LIMITED": "Only loosely related, incomplete, or based on inference.",
    "INSUFFICIENT": "Too incomplete to inform the hypothesis.",
    "NOT_ASSESSED": "The investigator has not yet assessed evidence strength.",
}

RELIABILITY_DESCRIPTIONS = {
    "HIGH": "Original, traceable, complete, and independently verifiable source.",
    "MODERATE": "Traceable but secondary, partial, or awaiting verification.",
    "LOW": "Unclear provenance, incomplete, or carrying unresolved conflicts.",
    "UNKNOWN": "Source quality cannot be determined from stored metadata.",
    "NOT_ASSESSED": "The investigator has not yet assessed source reliability.",
}

ASSESSMENT_DESCRIPTIONS = {
    "SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE": (
        "Reviewed supporting evidence exists, at least part of it is verified or strong, "
        "and no reviewed evidence currently conflicts."
    ),
    "PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE": (
        "Reviewed supporting evidence exists but it is limited or not independently verified, "
        "and no reviewed evidence currently conflicts."
    ),
    "MIXED_EVIDENCE": (
        "Both reviewed supporting and reviewed contradicting evidence are present."
    ),
    "LIMITED_SUPPORT": (
        "Only neutral or contextual evidence has been reviewed; it does not directly support the explanation."
    ),
    "SIGNIFICANT_CONTRADICTIONS": (
        "Reviewed contradictions or unresolved conflicts outweigh the available support."
    ),
    "INSUFFICIENT_INFORMATION": (
        "Too little reviewed evidence exists to assess the explanation."
    ),
    "NOT_YET_EVALUATED": (
        "No linked evidence has been evaluated for this hypothesis."
    ),
}
