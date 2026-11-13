from datetime import date
from datetime import datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)

class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    records_json: Mapped[str] = mapped_column(Text, nullable=False)
    validation_errors: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Other")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    processing_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")


class ReconstructedEvent(Base):
    __tablename__ = "reconstructed_events"
    event_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    person_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_precision: Mapped[str] = mapped_column(String(24), nullable=False)
    date_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    original_date_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_interpretation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    location_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    temporal_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NORMAL")
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    classification_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    extracted_record_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_field: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TemporalFinding(Base):
    __tablename__ = "temporal_findings"
    finding_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=True, index=True)
    related_event_id: Mapped[str | None] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=True, index=True)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNRESOLVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TemporalRelationship(Base):
    __tablename__ = "temporal_relationships"
    relationship_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False, index=True)
    related_event_id: Mapped[str] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(16), nullable=False)
    temporal_certainty: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TimelineSnapshot(Base):
    __tablename__ = "timeline_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reconstruction_metadata: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class EventAudit(Base):
    __tablename__ = "event_audits"
    audit_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    previous_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

Index("ix_event_source_evidence_record", EventSource.event_id, EventSource.evidence_id, EventSource.extracted_record_id, unique=True)
Index("ix_temporal_relationship_pair", TemporalRelationship.event_id, TemporalRelationship.related_event_id, unique=True)
