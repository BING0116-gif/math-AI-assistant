"""add durable daily learning plans"""
from alembic import op
import sqlalchemy as sa

revision = "kl60718293a9"
down_revision = "ij60718293a8"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_learning_plans_user_date"),
        sa.CheckConstraint("status IN ('active','completed','expired','cancelled')", name="ck_learning_plan_status"),
    )
    op.create_index("ix_learning_plans_user_status", "learning_plans", ["user_id", "status"])
    op.create_index("ix_learning_plans_plan_date", "learning_plans", ["plan_date"])
    op.create_table(
        "learning_plan_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("learning_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("knowledge_point", sa.String(128), nullable=True),
        sa.Column("question_id", sa.String(20), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.UniqueConstraint("plan_id", "sequence", name="uq_learning_plan_task_sequence"),
        sa.CheckConstraint("status IN ('pending','in_progress','completed','skipped','failed','expired')", name="ck_learning_plan_task_status"),
    )
    op.create_index("ix_learning_plan_tasks_plan_id", "learning_plan_tasks", ["plan_id"])
    op.create_index("ix_learning_plan_tasks_user_status", "learning_plan_tasks", ["user_id", "status"])

def downgrade():
    op.drop_table("learning_plan_tasks")
    op.drop_table("learning_plans")
