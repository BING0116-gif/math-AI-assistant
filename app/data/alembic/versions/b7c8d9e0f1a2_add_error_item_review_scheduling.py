"""T02 ReviewScheduler: error-item-level review scheduling fields

Revision ID: b7c8d9e0f1a2
Revises: ae5f60718293
"""
import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "ae5f60718293"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps the migration valid for the explicitly configured local
    # SQLite development database as well as the production PostgreSQL target.
    with op.batch_alter_table("error_items") as batch:
        batch.add_column(sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("review_interval_days", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("review_streak", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("scheduler_version", sa.String(40), nullable=False, server_default=""))
        batch.create_index("ix_error_item_owner_next_review", ["user_id", "next_review_at"])


def downgrade() -> None:
    with op.batch_alter_table("error_items") as batch:
        batch.drop_index("ix_error_item_owner_next_review")
        for name in ("scheduler_version", "review_streak", "review_interval_days", "next_review_at"):
            batch.drop_column(name)
