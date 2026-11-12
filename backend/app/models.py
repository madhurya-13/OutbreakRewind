from datetime import date
from datetime import datetime
from sqlalchemy import Date, DateTime, Integer, String, Text
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
