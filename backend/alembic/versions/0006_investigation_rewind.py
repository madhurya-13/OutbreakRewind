"""Add the Milestone 7 investigation history, versioning, snapshot, comparison, and export schema.

This migration is additive and does not alter Milestone 1-6 tables. The application's startup
create_all() creates these tables for local SQLite databases, so every operation is guarded with
IF NOT EXISTS to allow Alembic to adopt an existing schema without data loss.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_investigation_rewind"
down_revision = "0005_hypothesis_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_history_events",
        sa.Column("event_id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("previous_state", sa.Text(), nullable=False),
        sa.Column("new_state", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("related_event_id", sa.String(48), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "historical_entity_versions",
        sa.Column("version_id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state_data", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(120), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "investigation_snapshots",
        sa.Column("snapshot_id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("snapshot_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("snapshot_type", sa.String(48), nullable=False),
        sa.Column("snapshot_data", sa.Text(), nullable=False),
        sa.Column("event_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("included_entity_counts", sa.Text(), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(16), nullable=False),
        sa.Column("integrity_hash", sa.String(64), nullable=False),
        sa.Column("integrity_status", sa.String(24), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "investigation_comparisons",
        sa.Column("comparison_id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("snapshot_a_id", sa.String(48), nullable=True),
        sa.Column("snapshot_b_id", sa.String(48), nullable=True),
        sa.Column("timestamp_a", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_b", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comparison_data", sa.Text(), nullable=False),
        sa.Column("comparison_summary", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "investigation_exports",
        sa.Column("export_id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("export_type", sa.String(16), nullable=False),
        sa.Column("cutoff_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_reference", sa.String(48), nullable=True),
        sa.Column("file_reference", sa.String(512), nullable=False),
        sa.Column("generated_by", sa.String(120), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("export_status", sa.String(24), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        if_not_exists=True,
    )
    for table, columns in {
        "investigation_history_events": ["investigation_id", "event_type", "entity_type", "entity_id", "recorded_at"],
        "historical_entity_versions": ["investigation_id", "entity_type", "entity_id", "recorded_at"],
        "investigation_snapshots": ["investigation_id", "snapshot_type", "event_cutoff", "created_at"],
        "investigation_comparisons": ["investigation_id"],
        "investigation_exports": ["investigation_id", "cutoff_timestamp"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column], if_not_exists=True)
    op.create_index("ix_history_investigation_recorded", "investigation_history_events", ["investigation_id", "recorded_at"], if_not_exists=True)
    op.create_index("ix_history_investigation_entity", "investigation_history_events", ["investigation_id", "entity_type", "entity_id"], if_not_exists=True)
    op.create_index("uq_historical_entity_version", "historical_entity_versions", ["entity_type", "entity_id", "version_number"], unique=True, if_not_exists=True)
    op.create_index("ix_snapshot_investigation_created", "investigation_snapshots", ["investigation_id", "created_at"], if_not_exists=True)


def downgrade() -> None:
    for table in ("investigation_exports", "investigation_comparisons", "investigation_snapshots", "historical_entity_versions", "investigation_history_events"):
        op.drop_table(table)
