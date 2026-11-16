"""Backfill append-only Rewind history from existing Milestone 2-6 records.

This is deliberately non-destructive: it never changes evidence, events, graph,
contradictions, hypotheses, or their existing history. It reconstructs the
recorded trail from timestamps already stored by earlier milestones, then creates
immutable milestone snapshots at representative cutoffs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import SessionLocal
from app.intelligence.rewind.history_recorder import (record_entity_version,
                                                       record_history_event)
from app.intelligence.rewind.snapshot_manager import create_snapshot
from app.intelligence.rewind.utils import aware, iso
from app.models import (Contradiction, EvidenceRecord, GraphSnapshot,
                        Hypothesis, HypothesisAssessment, HypothesisVersion,
                        InvestigationHistoryEvent, InvestigationSnapshot,
                        ReconstructedEvent, TimelineSnapshot)

INVESTIGATION_ID = "ORION-001"


def _exists(db, event_type: str, entity_id: str) -> bool:
    return db.scalar(select(InvestigationHistoryEvent.event_id).where(
        InvestigationHistoryEvent.investigation_id == INVESTIGATION_ID,
        InvestigationHistoryEvent.event_type == event_type,
        InvestigationHistoryEvent.entity_id == entity_id,
    ).limit(1)) is not None


def main() -> None:
    with SessionLocal() as db:
        evidence = list(db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == INVESTIGATION_ID).order_by(EvidenceRecord.uploaded_at.asc())).all())
        events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == INVESTIGATION_ID).order_by(ReconstructedEvent.created_at.asc())).all())
        hypotheses = list(db.scalars(select(Hypothesis).where(Hypothesis.investigation_id == INVESTIGATION_ID).order_by(Hypothesis.created_at.asc())).all())
        hypothesis_versions = list(db.scalars(select(HypothesisVersion).order_by(HypothesisVersion.created_at.asc())).all())
        assessments = list(db.scalars(select(HypothesisAssessment).order_by(HypothesisAssessment.evaluated_at.asc())).all())
        contradictions = list(db.scalars(select(Contradiction).where(Contradiction.investigation_id == INVESTIGATION_ID).order_by(Contradiction.first_detected_at.asc())).all())
        timeline_snapshots = list(db.scalars(select(TimelineSnapshot).where(TimelineSnapshot.investigation_id == INVESTIGATION_ID).order_by(TimelineSnapshot.generated_at.asc())).all())
        graph_snapshots = list(db.scalars(select(GraphSnapshot).where(GraphSnapshot.investigation_id == INVESTIGATION_ID).order_by(GraphSnapshot.created_at.asc())).all())

        moments = [aware(item.uploaded_at) for item in evidence] + [aware(item.created_at) for item in events] + [aware(item.created_at) for item in hypotheses] + [aware(item.first_detected_at) for item in contradictions]
        moments = [item for item in moments if item]
        if moments and not _exists(db, "INVESTIGATION_CREATED", INVESTIGATION_ID):
            record_history_event(
                db, INVESTIGATION_ID, "INVESTIGATION_CREATED", "INVESTIGATION", INVESTIGATION_ID,
                "Project Orion investigation record was created.", new_state={"investigation_name": "Project Orion", "status": "Active"},
                actor_type="SYSTEM", actor_id="initial_import", recorded_at=min(moments),
            )

        for item in evidence:
            if _exists(db, "EVIDENCE_UPLOADED", item.id):
                continue
            state = {
                "evidence_id": item.id, "filename": item.filename, "format": item.format,
                "status": item.status, "uploaded_at": iso(item.uploaded_at), "category": item.category,
                "checksum": item.checksum, "record_count": item.record_count,
                "records": json.loads(item.records_json),
            }
            record_entity_version(db, INVESTIGATION_ID, "EVIDENCE_DOCUMENT", item.id, state, recorded_by="system", change_reason="Backfilled from stored evidence metadata", valid_from=item.uploaded_at, recorded_at=item.uploaded_at, source_reference={"evidence_id": item.id})
            record_history_event(
                db, INVESTIGATION_ID, "EVIDENCE_UPLOADED", "EVIDENCE_DOCUMENT", item.id,
                f"Evidence '{item.filename}' was uploaded and extracted.", new_state=state,
                actor_type="SYSTEM", actor_id="backfill", source_reference={"evidence_id": item.id},
                metadata={"record_count": item.record_count, "backfilled": True}, recorded_at=item.uploaded_at,
            )

        for item in events:
            if _exists(db, "EVENT_CREATED", item.event_id):
                continue
            state = {
                "event_id": item.event_id, "event_type": item.event_type, "event_description": item.event_description,
                "event_date": iso(item.event_date), "event_end_date": iso(item.event_end_date),
                "date_precision": item.date_precision, "person_id": item.person_id,
                "location_id": item.location_id, "location_name": item.location_name,
                "temporal_status": item.temporal_status, "verification_status": item.verification_status,
                "recorded_at": iso(item.recorded_at), "recorded_from_backfill": True,
            }
            record_entity_version(db, INVESTIGATION_ID, "RECONSTRUCTED_EVENT", item.event_id, state, recorded_by="system", change_reason="Backfilled from reconstructed event", valid_from=item.created_at, recorded_at=item.created_at, source_reference={"event_id": item.event_id})
            record_history_event(
                db, INVESTIGATION_ID, "EVENT_CREATED", "RECONSTRUCTED_EVENT", item.event_id,
                f"Reconstructed event '{item.event_description}' entered the timeline record.",
                new_state=state, actor_type="SYSTEM", actor_id="backfill",
                source_reference={"event_id": item.event_id}, recorded_at=item.created_at,
            )

        for item in timeline_snapshots:
            entity = f"TIMELINE-{item.version_number}"
            if _exists(db, "TIMELINE_RECONSTRUCTED", entity):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "TIMELINE_RECONSTRUCTED", "TIMELINE", entity,
                f"Timeline version {item.version_number} was recorded with {item.event_count} events.",
                new_state={"version_number": item.version_number, "event_count": item.event_count},
                actor_type="SYSTEM", actor_id="backfill", recorded_at=item.generated_at,
            )

        for item in graph_snapshots:
            entity = f"GRAPH-{item.snapshot_version}"
            if _exists(db, "NETWORK_RECONSTRUCTED", entity):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "NETWORK_RECONSTRUCTED", "GRAPH", entity,
                f"Network version {item.snapshot_version} was recorded with {item.node_count} nodes and {item.relationship_count} relationships.",
                new_state={"version_number": item.snapshot_version, "node_count": item.node_count, "relationship_count": item.relationship_count},
                actor_type="SYSTEM", actor_id="backfill", recorded_at=item.created_at,
            )

        for item in contradictions:
            if _exists(db, "CONTRADICTION_DETECTED", item.contradiction_id):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "CONTRADICTION_DETECTED", "CONTRADICTION", item.contradiction_id,
                f"Contradiction '{item.title}' was detected and requires investigator review.",
                new_state={"status": item.status, "severity": item.severity, "type": item.contradiction_type},
                actor_type="SYSTEM", actor_id="backfill", source_reference={"contradiction_id": item.contradiction_id},
                recorded_at=item.first_detected_at,
            )

        for item in hypotheses:
            if _exists(db, "HYPOTHESIS_CREATED", item.id):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "HYPOTHESIS_CREATED", "HYPOTHESIS", item.id,
                f"Competing hypothesis '{item.title}' was created.",
                new_state={"hypothesis_id": item.id, "title": item.title, "status": item.status},
                actor_type="INVESTIGATOR", actor_id=item.created_by, recorded_at=item.created_at,
            )

        for item in hypothesis_versions:
            entity = f"{item.hypothesis_id}:v{item.version_number}"
            if _exists(db, "HYPOTHESIS_VERSION_CREATED", entity):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "HYPOTHESIS_VERSION_CREATED", "HYPOTHESIS_VERSION", entity,
                f"Hypothesis version {item.version_number} was recorded: {item.change_description}",
                new_state={"version_number": item.version_number, "reason": item.reason},
                actor_type="INVESTIGATOR", actor_id=item.changed_by, recorded_at=item.created_at,
            )

        for item in assessments:
            if _exists(db, "HYPOTHESIS_EVALUATED", item.id):
                continue
            record_history_event(
                db, INVESTIGATION_ID, "HYPOTHESIS_EVALUATED", "HYPOTHESIS_ASSESSMENT", item.id,
                f"Hypothesis {item.hypothesis_id} was assessed as {item.assessment_label}.",
                new_state={"hypothesis_id": item.hypothesis_id, "assessment_label": item.assessment_label},
                actor_type="SYSTEM", actor_id="backfill", recorded_at=item.evaluated_at,
            )

        db.commit()

        # Create immutable milestone snapshots at representative observed cutoffs.
        history = list(db.scalars(select(InvestigationHistoryEvent).where(
            InvestigationHistoryEvent.investigation_id == INVESTIGATION_ID
        ).order_by(InvestigationHistoryEvent.recorded_at.asc())).all())
        existing_names = {item.snapshot_name for item in db.scalars(select(InvestigationSnapshot).where(
            InvestigationSnapshot.investigation_id == INVESTIGATION_ID
        )).all()}
        moments = [aware(item.recorded_at) for item in history if aware(item.recorded_at)]
        if moments:
            stage_names = ["Stage 1 - Initial investigation", "Stage 2 - Additional evidence", "Stage 3 - Investigator review", "Stage 4 - New findings", "Stage 5 - Current state"]
            fractions = [0.15, 0.35, 0.55, 0.75, 1.0]
            for index, (name, fraction) in enumerate(zip(stage_names, fractions), start=1):
                if name in existing_names:
                    continue
                cutoff = moments[min(len(moments) - 1, max(0, int(len(moments) * fraction) - 1))]
                create_snapshot(
                    db, INVESTIGATION_ID, snapshot_type="MILESTONE_SNAPSHOT" if index < 5 else "MANUAL_SNAPSHOT",
                    created_by="demo_seed", name=name,
                    description=f"Recorded state at representative Project Orion history checkpoint {index}.",
                    event_cutoff=cutoff,
                )
                db.commit()
        print(f"Backfill complete: {len(evidence)} evidence, {len(events)} events, {len(contradictions)} contradictions, {len(hypotheses)} hypotheses.")


if __name__ == "__main__":
    main()