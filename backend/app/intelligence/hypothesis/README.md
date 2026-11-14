# Hypothesis Intelligence Engine

Milestone 6 adds a deterministic, explainable reasoning layer over the evidence,
timeline, network, contradiction, and temporal data created in Milestones 1-5.

## Module map

| Module | Responsibility |
|---|---|
| `hypothesis_manager.py` | Create, edit, status, archive, list, notes, investigation summary and the `evaluate_investigation_hypotheses` orchestrator. |
| `evidence_linker.py` | Link, update, withdraw and list evidence-to-hypothesis relationships. Enforces duplicate protection and preserves provenance snapshots. |
| `evidence_assessor.py` | Suggests evidence strength and generates the default strength explanation. Strength is specific to one hypothesis. |
| `source_reliability.py` | Suggests source reliability from provenance and verification metadata. Reliability is independent of whether the source supports a hypothesis. |
| `hypothesis_evaluator.py` | Applies the documented qualitative rules and persists append-only assessments. |
| `hypothesis_comparator.py` | Builds a side-by-side matrix, shared-source insights, and the non-determinative comparison disclaimer. |
| `evidence_impact_analyzer.py` | Creates impact records after evidence, timeline, network, contradiction, or link changes; records investigator review. |
| `hypothesis_versioning.py` | Append-only hypothesis versions containing resulting state, previous state, evidence-link state, actor, and reason. |
| `hypothesis_explainer.py` | Deterministic narrative explanations. No external LLM is required or called. |
| `hypothesis_validator.py` (implemented as `validator.py`) | Category, status, duplicate-title, ownership, and text validation. |
| `source_catalog.py` | Resolves and snapshots existing investigation records for the linking interface. |

## Evaluation rules (version 6.2)

1. Withdrawn links are excluded from counts but retained in history.
2. Only links whose **review status** is `REVIEWED` or `VERIFIED` contribute to
   support, contradiction, or context decisions. Pending links are provisional.
3. `SIGNIFICANT_CONTRADICTIONS` when at least two linked contradictions remain
   unresolved, or when an unresolved contradiction combines with reviewed
   contradicting evidence, or when reviewed contradictions (at least two)
   outnumber reviewed supporting links.
4. `MIXED_EVIDENCE` when both reviewed supporting and reviewed contradicting
   links exist and rule 3 does not apply.
5. `SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE` when reviewed supporting
   links exist, no reviewed contradiction exists, and at least one reviewed
   supporting link is `STRONG` or `VERIFIED`.
6. `PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE` when reviewed supporting links
   exist with no reviewed contradiction and no strong/verified support.
7. `LIMITED_SUPPORT` when only reviewed neutral or contextual links exist.
8. `INSUFFICIENT_INFORMATION` when nothing has been reviewed or verified.
9. `NOT_YET_EVALUATED` when no non-withdrawn link exists.

These are review-workflow thresholds, not measures of scientific certainty.
The engine never produces probabilities, percentages, or an automatically
selected "correct" hypothesis.

## Source snapshots

Every link stores `source_snapshot` at link time (title, type, reference, date,
verification status, and selected details). If a source is later corrected,
withdrawn, or deleted, the snapshot remains inspectable and the evaluator marks
the source as unavailable and raises missing-information severity.

## Impact analysis

`analyze_source_change()` is called by the upload, timeline verification,
graph review, contradiction detection/review, and evidence-link routes. It:

1. resolves the changed source;
2. finds linked hypotheses and recalculates only their evaluations;
3. creates `REQUIRES_INVESTIGATOR_REVIEW` records where no link exists;
4. preserves the previous assessment label on every record;
5. never changes a hypothesis status.

An investigator reviews and closes an impact record through
`POST /api/hypotheses/{hypothesis_id}/impact/{impact_id}/review`.
