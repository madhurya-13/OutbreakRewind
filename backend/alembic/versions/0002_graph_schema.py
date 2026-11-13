"""Add Milestone 4 graph intelligence tables."""
from alembic import op
import sqlalchemy as sa

revision = "0002_graph_schema"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("graph_nodes",
        sa.Column("node_id", sa.String(96), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("node_type", sa.String(24), nullable=False), sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("display_label", sa.String(255), nullable=False), sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("graph_relationships",
        sa.Column("relationship_id", sa.String(96), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("source_node_id", sa.String(96), sa.ForeignKey("graph_nodes.node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", sa.String(96), sa.ForeignKey("graph_nodes.node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False), sa.Column("relationship_classification", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Float()), sa.Column("derivation_method", sa.String(120), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()), sa.Column("verification_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("relationship_sources",
        sa.Column("source_id", sa.Integer(), primary_key=True), sa.Column("relationship_id", sa.String(96), sa.ForeignKey("graph_relationships.relationship_id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.String(32)), sa.Column("reconstructed_event_id", sa.String(48), sa.ForeignKey("reconstructed_events.event_id", ondelete="CASCADE")),
        sa.Column("extracted_record_id", sa.String(80)), sa.Column("source_description", sa.Text(), nullable=False))
    op.create_table("graph_snapshots",
        sa.Column("snapshot_id", sa.String(96), primary_key=True), sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False), sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("relationship_count", sa.Integer(), nullable=False), sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("relationship_review_history",
        sa.Column("review_id", sa.String(96), primary_key=True), sa.Column("relationship_id", sa.String(96), sa.ForeignKey("graph_relationships.relationship_id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_status", sa.String(24), nullable=False), sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=False), sa.Column("action_timestamp", sa.DateTime(timezone=True), nullable=False))
    op.create_index("uq_graph_node_entity", "graph_nodes", ["investigation_id", "node_type", "entity_id"], unique=True)
    op.create_index("uq_graph_relationship_pair", "graph_relationships", ["investigation_id", "source_node_id", "target_node_id", "relationship_type"], unique=True)
    op.create_index("uq_relationship_source", "relationship_sources", ["relationship_id", "evidence_id", "reconstructed_event_id", "extracted_record_id"], unique=True)
    for table, columns in {"graph_nodes": ["investigation_id", "node_type"], "graph_relationships": ["investigation_id", "relationship_type", "verification_status", "source_node_id", "target_node_id"], "relationship_sources": ["relationship_id", "evidence_id", "reconstructed_event_id"], "graph_snapshots": ["investigation_id"], "relationship_review_history": ["relationship_id"]}.items():
        for column in columns: op.create_index(f"ix_{table}_{column}", table, [column])

def downgrade() -> None:
    for table in ("relationship_review_history", "graph_snapshots", "relationship_sources", "graph_relationships", "graph_nodes"): op.drop_table(table)
