"""phase3 exam and tutor persistence foundation

Revision ID: aa1b2c3d4e5f
Revises: a9c0d1e2f3a4
"""
import sqlalchemy as sa
from alembic import op

revision = "aa1b2c3d4e5f"
down_revision = "a9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("assessment_draft_answers", "practice_session_draft_answers")
    op.drop_index("ix_assessment_draft_answers_user_id", table_name="practice_session_draft_answers")
    op.drop_index("ix_assessment_draft_answers_session_id", table_name="practice_session_draft_answers")
    op.create_index("ix_practice_session_draft_answers_user_id", "practice_session_draft_answers", ["user_id"])
    op.create_index("ix_practice_session_draft_answers_session_id", "practice_session_draft_answers", ["session_id"])
    with op.batch_alter_table("practice_session_draft_answers") as batch:
        batch.drop_constraint("uq_assessment_draft_question", type_="unique")
        batch.create_unique_constraint("uq_practice_session_draft_question", ["session_id", "session_question_id"])
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("default_tutor_mode", sa.String(30), nullable=False, server_default="step_by_step"))
        batch.add_column(sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "ai_interaction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("chat_session_id", sa.String(36), nullable=True),
        sa.Column("practice_session_id", sa.String(36), nullable=True),
        sa.Column("request_kind", sa.String(40), nullable=False),
        sa.Column("tutor_mode", sa.String(30), nullable=True),
        sa.Column("intent", sa.String(80), nullable=True),
        sa.Column("course_id", sa.String(36), nullable=True),
        sa.Column("knowledge_point_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("tool_names", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(80), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="started"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["practice_session_id"], ["practice_sessions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_interaction_runs_user_id", "ai_interaction_runs", ["user_id"])
    op.create_index("ix_ai_interaction_runs_chat_session_id", "ai_interaction_runs", ["chat_session_id"])
    op.create_index("ix_ai_interaction_runs_practice_session_id", "ai_interaction_runs", ["practice_session_id"])
    op.create_index("ix_ai_interaction_runs_request_kind", "ai_interaction_runs", ["request_kind"])
    op.create_index("ix_ai_interaction_runs_status", "ai_interaction_runs", ["status"])
    op.create_index("ix_ai_interaction_owner_created", "ai_interaction_runs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_interaction_owner_created", table_name="ai_interaction_runs")
    op.drop_index("ix_ai_interaction_runs_status", table_name="ai_interaction_runs")
    op.drop_index("ix_ai_interaction_runs_request_kind", table_name="ai_interaction_runs")
    op.drop_index("ix_ai_interaction_runs_practice_session_id", table_name="ai_interaction_runs")
    op.drop_index("ix_ai_interaction_runs_chat_session_id", table_name="ai_interaction_runs")
    op.drop_index("ix_ai_interaction_runs_user_id", table_name="ai_interaction_runs")
    op.drop_table("ai_interaction_runs")
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_column("context_snapshot")
        batch.drop_column("default_tutor_mode")
    with op.batch_alter_table("practice_session_draft_answers") as batch:
        batch.drop_constraint("uq_practice_session_draft_question", type_="unique")
        batch.create_unique_constraint("uq_assessment_draft_question", ["session_id", "session_question_id"])
    op.drop_index("ix_practice_session_draft_answers_user_id", table_name="practice_session_draft_answers")
    op.drop_index("ix_practice_session_draft_answers_session_id", table_name="practice_session_draft_answers")
    op.create_index("ix_assessment_draft_answers_user_id", "practice_session_draft_answers", ["user_id"])
    op.create_index("ix_assessment_draft_answers_session_id", "practice_session_draft_answers", ["session_id"])
    op.rename_table("practice_session_draft_answers", "assessment_draft_answers")
