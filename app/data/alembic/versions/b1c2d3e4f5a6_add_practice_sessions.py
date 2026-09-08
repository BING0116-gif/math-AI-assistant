"""add owner-bound practice sessions and immutable attempts

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
"""

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="practice"),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_graph_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_practice_session_owner_idempotency"),
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])
    op.create_index("ix_practice_sessions_course_id", "practice_sessions", ["course_id"])
    op.create_index("ix_practice_sessions_version_id", "practice_sessions", ["version_id"])
    op.create_index("ix_practice_sessions_status", "practice_sessions", ["status"])
    op.create_index("ix_practice_session_owner_status", "practice_sessions", ["user_id", "status"])
    op.create_table(
        "practice_session_questions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="1"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "position", name="uq_practice_session_position"),
        sa.UniqueConstraint("session_id", "question_id", name="uq_practice_session_question"),
    )
    op.create_index("ix_practice_session_questions_session_id", "practice_session_questions", ["session_id"])
    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("session_question_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("user_answer", sa.JSON()),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("grading_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_question_id"], ["practice_session_questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_question_id", name="uq_practice_attempt_session_question"),
        sa.UniqueConstraint("user_id", "session_id", "idempotency_key", name="uq_practice_attempt_idempotency"),
    )
    op.create_index("ix_practice_attempts_user_id", "practice_attempts", ["user_id"])
    op.create_index("ix_practice_attempts_session_id", "practice_attempts", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_practice_attempts_session_id", table_name="practice_attempts")
    op.drop_index("ix_practice_attempts_user_id", table_name="practice_attempts")
    op.drop_table("practice_attempts")
    op.drop_index("ix_practice_session_questions_session_id", table_name="practice_session_questions")
    op.drop_table("practice_session_questions")
    op.drop_index("ix_practice_session_owner_status", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_status", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_version_id", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_course_id", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_user_id", table_name="practice_sessions")
    op.drop_table("practice_sessions")
