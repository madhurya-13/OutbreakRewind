"""Add investigator-controlled hypothesis management tables."""
from alembic import op
import sqlalchemy as sa

revision = "0004_hypotheses"
down_revision = "0003_contradictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("hypotheses",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("investigation_id", sa.String(80), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detailed_explanation", sa.Text(), nullable=False),
        sa.Column("assumptions", sa.Text(), nullable=False),
        sa.Column("predictions", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("open_questions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("current_assessment", sa.String(64), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_evidence_links",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False), sa.Column("source_id", sa.String(120), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("relevant_observations", sa.Text(), nullable=False), sa.Column("evidence_strength", sa.String(16), nullable=False),
        sa.Column("source_reliability", sa.String(16), nullable=False), sa.Column("strength_reason", sa.Text(), nullable=False),
        sa.Column("reliability_reason", sa.Text(), nullable=False), sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("investigator_notes", sa.Text(), nullable=False), sa.Column("linked_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_assessments",
        sa.Column("id", sa.String(48), primary_key=True), sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessment_label", sa.String(64), nullable=False), sa.Column("assessment_summary", sa.Text(), nullable=False),
        sa.Column("supporting_count", sa.Integer(), nullable=False), sa.Column("contradicting_count", sa.Integer(), nullable=False),
        sa.Column("neutral_count", sa.Integer(), nullable=False), sa.Column("contextual_count", sa.Integer(), nullable=False),
        sa.Column("verified_count", sa.Integer(), nullable=False), sa.Column("pending_review_count", sa.Integer(), nullable=False),
        sa.Column("strong_count", sa.Integer(), nullable=False), sa.Column("moderate_count", sa.Integer(), nullable=False),
        sa.Column("limited_count", sa.Integer(), nullable=False), sa.Column("unresolved_contradiction_count", sa.Integer(), nullable=False),
        sa.Column("missing_information", sa.Text(), nullable=False), sa.Column("assessment_details", sa.Text(), nullable=False),
        sa.Column("evaluation_rule_version", sa.String(32), nullable=False), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_versions",
        sa.Column("id", sa.String(48), primary_key=True), sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("snapshot_data", sa.Text(), nullable=False),
        sa.Column("change_description", sa.Text(), nullable=False), sa.Column("changed_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_impact_records",
        sa.Column("id", sa.String(48), primary_key=True), sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False), sa.Column("source_id", sa.String(120), nullable=False),
        sa.Column("impact_category", sa.String(32), nullable=False), sa.Column("previous_assessment", sa.String(64), nullable=False),
        sa.Column("current_assessment", sa.String(64), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False), sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_notes",
        sa.Column("id", sa.String(48), primary_key=True), sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False), sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("hypothesis_review_history",
        sa.Column("id", sa.String(48), primary_key=True), sa.Column("hypothesis_id", sa.String(48), sa.ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False), sa.Column("previous_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("performed_by", sa.String(120), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("uq_hypothesis_title", "hypotheses", ["investigation_id", "title"], unique=True)
    op.create_index("uq_hypothesis_source", "hypothesis_evidence_links", ["hypothesis_id", "source_type", "source_id"], unique=True)
    op.create_index("uq_hypothesis_version", "hypothesis_versions", ["hypothesis_id", "version_number"], unique=True)
    for table, columns in {
        "hypotheses": ["investigation_id", "status", "updated_at"],
        "hypothesis_evidence_links": ["hypothesis_id", "source_type", "source_id", "review_status"],
        "hypothesis_assessments": ["hypothesis_id", "evaluated_at"],
        "hypothesis_versions": ["hypothesis_id"],
        "hypothesis_impact_records": ["hypothesis_id", "created_at"],
        "hypothesis_notes": ["hypothesis_id"],
        "hypothesis_review_history": ["hypothesis_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("hypothesis_review_history", "hypothesis_notes", "hypothesis_impact_records",
                  "hypothesis_versions", "hypothesis_assessments", "hypothesis_evidence_links", "hypotheses"):
        op.drop_table(table)
