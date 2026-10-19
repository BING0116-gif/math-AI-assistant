"""add owner-scoped learning goals"""
from alembic import op
import sqlalchemy as sa

revision = "ij60718293a8"
down_revision = "hi60718293a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("goal_type", sa.String(length=32), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("target_knowledge_point", sa.String(length=128), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("goal_type IN ('minutes','attempts','mastery')", name="ck_learning_goal_type"),
        sa.CheckConstraint("target_value > 0", name="ck_learning_goal_target_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_goals_user_id", "learning_goals", ["user_id"])
    op.create_index("ix_learning_goals_user_status", "learning_goals", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_learning_goals_user_status", table_name="learning_goals")
    op.drop_index("ix_learning_goals_user_id", table_name="learning_goals")
    op.drop_table("learning_goals")
