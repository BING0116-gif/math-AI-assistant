"""add spaced review workflow fields and idempotent actions

Revision ID: a8b9c0d1e2f3
Revises: a7b8c9d0e1f2
"""
import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_schedules") as batch:
        batch.add_column(sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("stage", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("algorithm_version", sa.String(40), nullable=False, server_default="spaced-review-v1"))
        batch.add_column(sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deferred_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "review_schedule_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["review_schedules.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_review_action_owner_key"),
    )
    op.create_index("ix_review_action_owner_schedule", "review_schedule_actions", ["user_id", "schedule_id"])


def downgrade() -> None:
    op.drop_index("ix_review_action_owner_schedule", table_name="review_schedule_actions")
    op.drop_table("review_schedule_actions")
    with op.batch_alter_table("review_schedules") as batch:
        for name in ("deferred_until", "last_reviewed_at", "algorithm_version", "stage", "review_count"):
            batch.drop_column(name)
