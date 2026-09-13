"""T11 add durable exam recovery snapshot.

Revision ID: c9d0e1f2a3b4
Revises: b8d9e0f1a2b3
"""
import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("practice_sessions") as batch:
        batch.add_column(sa.Column("recovery_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("recovery_snapshot_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("practice_sessions") as batch:
        batch.drop_column("recovery_snapshot_at")
        batch.drop_column("recovery_snapshot")
