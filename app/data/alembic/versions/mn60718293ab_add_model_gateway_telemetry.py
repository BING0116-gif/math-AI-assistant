"""add model gateway telemetry fields"""
from alembic import op
import sqlalchemy as sa
revision = "mn60718293ab"
down_revision = "lm60718293aa"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("ai_interaction_runs", sa.Column("provider", sa.String(60), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("request_id", sa.String(128), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("fallback_reason", sa.String(200), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("quality_flags", sa.JSON(), nullable=True))
    op.create_index("ix_ai_interaction_runs_request_id", "ai_interaction_runs", ["request_id"])
    # Keep implicit ORM indexes explicit so Alembic check is clean on a fresh DB.
    op.create_index("ix_learning_plans_user_id", "learning_plans", ["user_id"])
    op.create_index("ix_learning_plans_goal_id", "learning_plans", ["goal_id"])
    op.create_index("ix_learning_plan_tasks_user_id", "learning_plan_tasks", ["user_id"])
    op.create_index("ix_proactive_learning_actions_user_id", "proactive_learning_actions", ["user_id"])
def downgrade():
    op.drop_index("ix_proactive_learning_actions_user_id", table_name="proactive_learning_actions")
    op.drop_index("ix_learning_plan_tasks_user_id", table_name="learning_plan_tasks")
    op.drop_index("ix_learning_plans_goal_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_user_id", table_name="learning_plans")
    op.drop_index("ix_ai_interaction_runs_request_id", table_name="ai_interaction_runs")
    for name in ("quality_flags", "fallback_reason", "request_id", "provider"): op.drop_column("ai_interaction_runs", name)
