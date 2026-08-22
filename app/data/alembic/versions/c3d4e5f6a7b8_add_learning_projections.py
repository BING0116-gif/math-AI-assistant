"""add rebuildable knowledge state and review schedule projections

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_knowledge_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("knowledge_point_code", sa.String(100), nullable=False),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_attempt_id", sa.String(36)),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_attempt_id"], ["practice_attempts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "knowledge_point_code", name="uq_user_knowledge_state_owner_code"),
    )
    op.create_index("ix_user_knowledge_state_owner_mastery", "user_knowledge_states", ["user_id", "mastery"])
    op.create_table(
        "review_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("knowledge_point_code", sa.String(100), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("consecutive_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_id", sa.String(36)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_attempt_id"], ["practice_attempts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "knowledge_point_code", name="uq_review_schedule_owner_code"),
    )
    op.create_index("ix_review_schedule_owner_due", "review_schedules", ["user_id", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_review_schedule_owner_due", table_name="review_schedules")
    op.drop_table("review_schedules")
    op.drop_index("ix_user_knowledge_state_owner_mastery", table_name="user_knowledge_states")
    op.drop_table("user_knowledge_states")
