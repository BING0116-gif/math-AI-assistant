"""add structured knowledge point learning content

Revision ID: c5d9e2f3a4b5
Revises: b4a8c1d2e3f4
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d9e2f3a4b5"
down_revision = "b4a8c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_points") as batch_op:
        batch_op.add_column(sa.Column("key_concepts", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("key_formulas", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("exam_focuses", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_points") as batch_op:
        batch_op.drop_column("exam_focuses")
        batch_op.drop_column("key_formulas")
        batch_op.drop_column("key_concepts")
