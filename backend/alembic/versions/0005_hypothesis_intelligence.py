"""Expand hypothesis intelligence with provenance snapshots and impact review.

Additive only: existing Milestone 1-5 rows and Milestone 6 rows are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_hypothesis_intelligence"
down_revision = "0004_hypotheses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hypotheses") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("hypothesis_evidence_links") as batch:
        batch.add_column(sa.Column("source_title", sa.String(255), nullable=False, server_default=""))
        batch.add_column(sa.Column("source_snapshot", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("reviewed_by", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("hypothesis_versions") as batch:
        batch.add_column(sa.Column("previous_data", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("reason", sa.Text(), nullable=False, server_default=""))

    with op.batch_alter_table("hypothesis_impact_records") as batch:
        batch.add_column(sa.Column("trigger", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("reviewed_by", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("review_note", sa.Text(), nullable=False, server_default=""))

    op.create_index("ix_hypothesis_evidence_links_source_title", "hypothesis_evidence_links", ["source_title"])
    op.create_index("ix_hypothesis_impact_records_reviewed", "hypothesis_impact_records", ["reviewed"])


def downgrade() -> None:
    op.drop_index("ix_hypothesis_impact_records_reviewed", table_name="hypothesis_impact_records")
    op.drop_index("ix_hypothesis_evidence_links_source_title", table_name="hypothesis_evidence_links")
    with op.batch_alter_table("hypothesis_impact_records") as batch:
        batch.drop_column("review_note")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("trigger")
    with op.batch_alter_table("hypothesis_versions") as batch:
        batch.drop_column("reason")
        batch.drop_column("previous_data")
    with op.batch_alter_table("hypothesis_evidence_links") as batch:
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("source_snapshot")
        batch.drop_column("source_title")
    with op.batch_alter_table("hypotheses") as batch:
        batch.drop_column("archived_at")
