"""add chapter release state

Revision ID: d3e4f5a6b7c8
Revises: d2e3f4a5b6c7
"""

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="published"))
        batch_op.add_column(sa.Column("published_by", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_chapters_status", ["status"])


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_index("ix_chapters_status")
        batch_op.drop_column("published_at")
        batch_op.drop_column("published_by")
        batch_op.drop_column("status")
