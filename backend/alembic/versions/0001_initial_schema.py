"""Create the Milestone 1-3 schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("events",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False), sa.Column("location", sa.String(120), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False), sa.Column("category", sa.String(80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("source", sa.String(80), nullable=False))
    op.create_table("evidence_records",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("investigation_id", sa.String(80), nullable=False), sa.Column("format", sa.String(8), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False), sa.Column("records_json", sa.Text(), nullable=False),
        sa.Column("validation_errors", sa.Text(), nullable=False), sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False), sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("processing_stage", sa.String(32), nullable=False))
    op.create_table("reconstructed_events",
        sa.Column("event_id", sa.String(48), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("person_id", sa.String(80)), sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("event_description", sa.Text(), nullable=False), sa.Column("event_date", sa.Date()),
        sa.Column("event_end_date", sa.Date()), sa.Column("date_precision", sa.String(24), nullable=False),
        sa.Column("date_confidence", sa.Float(), nullable=False), sa.Column("original_date_value", sa.Text()),
        sa.Column("date_interpretation", sa.String(64)), sa.Column("report_date", sa.Date()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False), sa.Column("location_id", sa.String(80)),
        sa.Column("location_name", sa.String(180)), sa.Column("temporal_status", sa.String(24), nullable=False),
        sa.Column("verification_status", sa.String(24), nullable=False), sa.Column("classification_confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_sources",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.String(32), nullable=False), sa.Column("extracted_record_id", sa.String(80)),
        sa.Column("source_page", sa.Integer()), sa.Column("source_row", sa.Integer()), sa.Column("source_field", sa.String(120)),
        sa.Column("original_value", sa.Text()), sa.Column("extraction_method", sa.String(64)))
    op.create_table("temporal_findings",
        sa.Column("finding_id", sa.String(48), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE")),
        sa.Column("related_event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE")),
        sa.Column("finding_type", sa.String(64), nullable=False), sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("temporal_relationships",
        sa.Column("relationship_id", sa.String(48), primary_key=True),
        sa.Column("event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(16), nullable=False), sa.Column("temporal_certainty", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("timeline_snapshots",
        sa.Column("snapshot_id", sa.String(48), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reconstruction_metadata", sa.Text(), nullable=False))
    op.create_table("event_audits",
        sa.Column("audit_id", sa.String(48), primary_key=True), sa.Column("event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False), sa.Column("previous_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False), sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False))
    for table, columns in {
        "events": ["date"], "evidence_records": ["investigation_id", "checksum", "status"],
        "reconstructed_events": ["investigation_id", "person_id", "event_type", "event_date", "location_id"],
        "event_sources": ["event_id", "evidence_id", "extracted_record_id"],
        "temporal_findings": ["investigation_id", "event_id", "related_event_id"],
        "temporal_relationships": ["event_id", "related_event_id"],
        "timeline_snapshots": ["investigation_id"], "event_audits": ["event_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("uq_event_source_evidence_record", "event_sources", ["event_id", "evidence_id", "extracted_record_id"], unique=True)
    op.create_index("uq_temporal_relationship_pair", "temporal_relationships", ["event_id", "related_event_id"], unique=True)

def downgrade() -> None:
    for table in ("event_audits", "timeline_snapshots", "temporal_relationships", "temporal_findings", "event_sources", "reconstructed_events", "evidence_records", "events"):
        op.drop_table(table)
