"""Add Milestone 5 contradiction intelligence tables."""
from alembic import op
import sqlalchemy as sa

revision = "0003_contradictions"
down_revision = "0002_graph_schema"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("contradictions",
        sa.Column("contradiction_id", sa.String(96), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("contradiction_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("machine_priority", sa.String(24), nullable=False),
        sa.Column("investigator_priority", sa.String(24)),
        sa.Column("affected_entity_type", sa.String(32)),
        sa.Column("affected_entity_id", sa.String(96)),
        sa.Column("affected_event_id", sa.String(48)),
        sa.Column("affected_relationship_id", sa.String(96)),
        sa.Column("detection_rule", sa.String(160), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("contradiction_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contradiction_id", sa.String(96), sa.ForeignKey("contradictions.contradiction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.String(32)), sa.Column("extracted_record_id", sa.String(80)),
        sa.Column("reconstructed_event_id", sa.String(48)), sa.Column("graph_edge_id", sa.String(96)),
        sa.Column("source_field", sa.String(120)), sa.Column("original_value", sa.Text()),
        sa.Column("normalized_value", sa.Text()), sa.Column("source_location", sa.String(120)),
        sa.Column("comparison_role", sa.String(16), nullable=False))
    op.create_table("contradiction_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contradiction_id", sa.String(96), sa.ForeignKey("contradictions.contradiction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(120), nullable=False), sa.Column("source_a_value", sa.Text(), nullable=False),
        sa.Column("source_b_value", sa.Text(), nullable=False), sa.Column("normalized_a_value", sa.Text(), nullable=False),
        sa.Column("normalized_b_value", sa.Text(), nullable=False), sa.Column("comparison_rule", sa.String(160), nullable=False),
        sa.Column("comparison_result", sa.String(64), nullable=False), sa.Column("explanation", sa.Text(), nullable=False))
    op.create_table("contradiction_reviews",
        sa.Column("review_id", sa.String(96), primary_key=True),
        sa.Column("contradiction_id", sa.String(96), sa.ForeignKey("contradictions.contradiction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer", sa.String(120), nullable=False), sa.Column("action", sa.String(32), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=False), sa.Column("previous_status", sa.String(24), nullable=False),
        sa.Column("new_status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("contradiction_snapshots",
        sa.Column("snapshot_id", sa.String(96), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False), sa.Column("detected_count", sa.Integer(), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False), sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("resolved_count", sa.Integer(), nullable=False), sa.Column("run_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False))
    op.create_index("uq_contradiction_identity", "contradictions", ["investigation_id", "contradiction_type", "affected_entity_id", "affected_event_id", "detection_rule"], unique=True)
    for table, columns in {"contradictions": ["investigation_id","contradiction_type","severity","status","affected_entity_type","affected_entity_id","affected_event_id"], "contradiction_evidence": ["contradiction_id","evidence_id","extracted_record_id","reconstructed_event_id"], "contradiction_comparisons": ["contradiction_id"], "contradiction_reviews": ["contradiction_id"], "contradiction_snapshots": ["investigation_id"]}.items():
        for column in columns: op.create_index(f"ix_{table}_{column}", table, [column])

def downgrade() -> None:
    for table in ("contradiction_snapshots","contradiction_reviews","contradiction_comparisons","contradiction_evidence","contradictions"):
        op.drop_table(table)
