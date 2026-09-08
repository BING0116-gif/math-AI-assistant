"""add intelligent assessment blueprint and draft persistence

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
"""
import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("practice_sessions") as batch:
        batch.add_column(sa.Column("duration_limit_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("completion_reason", sa.String(30), nullable=True))
    op.create_table(
        "assessment_blueprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False, unique=True),
        sa.Column("schema_version", sa.String(20), nullable=False, server_default="1"),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("planning_source", sa.String(30), nullable=False),
        sa.Column("input_signal_snapshot", sa.JSON(), nullable=False),
        sa.Column("blueprint_json", sa.JSON(), nullable=False),
        sa.Column("deviations_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_usage", sa.JSON()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_assessment_blueprints_user_id", "assessment_blueprints", ["user_id"])
    op.create_table(
        "assessment_draft_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("session_question_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.JSON()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_question_id"], ["practice_session_questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "session_question_id", name="uq_assessment_draft_question"),
    )
    op.create_index("ix_assessment_draft_answers_user_id", "assessment_draft_answers", ["user_id"])
    op.create_index("ix_assessment_draft_answers_session_id", "assessment_draft_answers", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_draft_answers_session_id", table_name="assessment_draft_answers")
    op.drop_index("ix_assessment_draft_answers_user_id", table_name="assessment_draft_answers")
    op.drop_table("assessment_draft_answers")
    op.drop_index("ix_assessment_blueprints_user_id", table_name="assessment_blueprints")
    op.drop_table("assessment_blueprints")
    with op.batch_alter_table("practice_sessions") as batch:
        batch.drop_column("completion_reason")
        batch.drop_column("duration_limit_seconds")
