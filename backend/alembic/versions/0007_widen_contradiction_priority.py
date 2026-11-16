"""Allow the stored contradiction priority explanation to exceed the original short label length.

SQLite does not enforce VARCHAR lengths, while PostgreSQL does. Existing ORION rows contain
machine-priority explanations up to 76 characters, so the original VARCHAR(24) schema cannot
hold the data that the application already writes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_contradiction_priority"
down_revision = "0006_investigation_rewind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contradictions") as batch_op:
        batch_op.alter_column(
            "machine_priority",
            existing_type=sa.String(24),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("contradictions") as batch_op:
        batch_op.alter_column(
            "machine_priority",
            existing_type=sa.Text(),
            type_=sa.String(24),
            existing_nullable=False,
        )