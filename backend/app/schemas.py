from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    date: date
    title: str
    location: str
    severity: str
    category: str
    summary: str
    source: str

class HealthRead(BaseModel):
    status: str
    database: str


class EventCorrection(BaseModel):
    actor: str = "investigator"
    event_description: str | None = None
    event_type: str | None = None
    person_id: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    event_date: date | None = None
    event_end_date: date | None = None
    temporal_status: Literal["NORMAL", "WARNING", "REQUIRES_REVIEW", "UNRESOLVED"] | None = None

class RelationshipReview(BaseModel):
    verification_status: Literal["VERIFIED", "REJECTED", "UNVERIFIED"]
    reviewer_note: str = ""

class ContradictionReviewRequest(BaseModel):
    reviewer: str = "investigator"
    action: Literal["UNDER_REVIEW", "CONFIRMED_CONFLICT", "RESOLVED", "DISMISSED", "REOPENED"]
    review_note: str = ""


HYPOTHESIS_CATEGORIES = {
    "COMMON_SOURCE_EXPOSURE", "PERSON_TO_PERSON_CONTACT", "SHARED_LOCATION_EXPOSURE",
    "MULTIPLE_INDEPENDENT_SOURCES", "ENVIRONMENTAL_EXPOSURE", "REPORTING_OR_DATA_ERROR",
    "UNKNOWN_OR_UNCLASSIFIED",
}

class HypothesisCreate(BaseModel):
    """Create a competing explanation inside one investigation."""
    title: str = Field(description="Distinct title within the investigation (3-180 characters).")
    category: str = Field(default="UNKNOWN_OR_UNCLASSIFIED", description="Documented category or an uppercase custom category.")
    description: str = Field(description="Short description of the competing explanation.")
    detailed_explanation: str = Field(default="", description="Longer investigator explanation and proposed sequence.")
    assumptions: list[str] = Field(default_factory=list, description="Initial assumptions behind the hypothesis.")
    predictions: list[str] = Field(default_factory=list, description="Expected observations or predictions.")
    limitations: list[str] = Field(default_factory=list, description="Known limitations of the explanation.")
    open_questions: list[str] = Field(default_factory=list, description="Questions the investigation still needs to answer.")
    initial_notes: str = Field(default="", description="Optional initial investigator note.")
    created_by: str = "investigator"

class HypothesisUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    description: str | None = None
    detailed_explanation: str | None = None
    assumptions: list[str] | None = None
    predictions: list[str] | None = None
    limitations: list[str] | None = None
    open_questions: list[str] | None = None
    reason: str = ""
    updated_by: str = "investigator"

class HypothesisStatusUpdate(BaseModel):
    status: Literal["DRAFT", "UNDER_INVESTIGATION", "SUPPORTED_BY_AVAILABLE_EVIDENCE", "CONTRADICTED_BY_AVAILABLE_EVIDENCE", "INCONCLUSIVE", "ARCHIVED"]
    explanation: str = ""
    updated_by: str = "investigator"

class HypothesisEvidenceCreate(BaseModel):
    source_type: Literal["EVIDENCE_DOCUMENT", "EXTRACTED_RECORD", "RECONSTRUCTED_EVENT", "GRAPH_RELATIONSHIP", "CONTRADICTION", "TEMPORAL_FINDING", "INVESTIGATOR_NOTE"]
    source_id: str
    classification: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL", "CONTEXTUAL"]
    explanation: str
    relevant_observations: str = ""
    evidence_strength: Literal["STRONG", "MODERATE", "LIMITED", "INSUFFICIENT", "NOT_ASSESSED"] = "NOT_ASSESSED"
    source_reliability: Literal["HIGH", "MODERATE", "LOW", "UNKNOWN", "NOT_ASSESSED"] = "NOT_ASSESSED"
    strength_reason: str = ""
    reliability_reason: str = ""
    investigator_notes: str = ""
    linked_by: str = "investigator"

class HypothesisEvidenceUpdate(BaseModel):
    classification: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL", "CONTEXTUAL"] | None = None
    explanation: str | None = None
    evidence_strength: Literal["STRONG", "MODERATE", "LIMITED", "INSUFFICIENT", "NOT_ASSESSED"] | None = None
    source_reliability: Literal["HIGH", "MODERATE", "LOW", "UNKNOWN", "NOT_ASSESSED"] | None = None
    strength_reason: str | None = None
    reliability_reason: str | None = None
    review_status: Literal["PENDING_REVIEW", "REVIEWED", "VERIFIED", "DISPUTED", "WITHDRAWN"] | None = None
    investigator_notes: str | None = None
    updated_by: str = "investigator"

class HypothesisCompareRequest(BaseModel):
    hypothesis_ids: list[str] = Field(min_length=2, max_length=6, description="Two to six hypotheses from the same investigation.")

class HypothesisNoteCreate(BaseModel):
    note: str
    created_by: str = "investigator"

class ImpactReviewRequest(BaseModel):
    reviewed_by: str = "investigator"
    explanation: str = ""


class HypothesisNoteUpdate(BaseModel):
    note: str
    updated_by: str = "investigator"
