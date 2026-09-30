"""add student papers and deterministic practice diagnostics

Revision ID: f9a0b1c2d3e4
Revises: f8a9b0c1d2e3
"""
from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "student_papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("knowledge_graph_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("blueprint_snapshot", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('manual','ai','recommended')", name="ck_student_paper_source_type"),
        sa.CheckConstraint("status IN ('draft','ready','archived')", name="ck_student_paper_status"),
    )
    op.create_index("ix_student_papers_user_id", "student_papers", ["user_id"])
    op.create_index("ix_student_papers_course_id", "student_papers", ["course_id"])
    op.create_index("ix_student_papers_version_id", "student_papers", ["version_id"])
    op.create_index("ix_student_papers_status", "student_papers", ["status"])
    op.create_index("ix_student_paper_owner_updated", "student_papers", ["user_id", "updated_at"])

    op.create_table(
        "student_paper_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("student_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(20), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="1"),
        sa.Column("question_snapshot", sa.JSON(), nullable=False),
        sa.Column("selection_reason", sa.JSON(), nullable=True),
        sa.UniqueConstraint("paper_id", "position", name="uq_student_paper_position"),
        sa.UniqueConstraint("paper_id", "question_id", name="uq_student_paper_question"),
    )
    op.create_index("ix_student_paper_questions_paper_id", "student_paper_questions", ["paper_id"])

    # Batch mode preserves SQLite test/local compatibility while emitting a
    # normal ALTER TABLE sequence on PostgreSQL.
    with op.batch_alter_table("practice_sessions") as batch_op:
        batch_op.add_column(sa.Column("source_paper_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key("fk_practice_sessions_source_paper", "student_papers", ["source_paper_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_practice_sessions_source_paper_id", "practice_sessions", ["source_paper_id"])

    op.create_table(
        "practice_diagnostic_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(20), sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("practice_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_code", sa.String(100), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("prompt_snapshot", sa.JSON(), nullable=False),
        sa.Column("selected_answer", sa.JSON(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_practice_diagnostic_owner_key"),
        sa.UniqueConstraint("attempt_id", "step_index", name="uq_practice_diagnostic_attempt_step"),
    )
    op.create_index("ix_practice_diagnostic_events_user_id", "practice_diagnostic_events", ["user_id"])
    op.create_index("ix_practice_diagnostic_events_session_id", "practice_diagnostic_events", ["session_id"])
    op.create_index("ix_practice_diagnostic_events_attempt_id", "practice_diagnostic_events", ["attempt_id"])


def downgrade():
    op.drop_table("practice_diagnostic_events")
    op.drop_index("ix_practice_sessions_source_paper_id", table_name="practice_sessions")
    with op.batch_alter_table("practice_sessions") as batch_op:
        batch_op.drop_constraint("fk_practice_sessions_source_paper", type_="foreignkey")
        batch_op.drop_column("source_paper_id")
    op.drop_table("student_paper_questions")
    op.drop_table("student_papers")
