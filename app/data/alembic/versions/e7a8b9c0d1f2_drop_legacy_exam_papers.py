"""Drop legacy exam_papers / exam_submissions tables.

The legacy per-user paper flow (ExamPaper/ExamSubmission) was fully replaced
by PracticeSession mode="exam" plus the admin Paper/PaperQuestion stack.
The models were removed from the codebase; this migration drops the orphaned
tables. Historical learning data lives on in learning_records /
practice_attempts, which are unrelated to these tables.

Revision ID: e7a8b9c0d1f2
Revises: d3e4f5a6b7c8
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7a8b9c0d1f2"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("exam_submissions")
    op.drop_index(op.f("ix_exam_papers_user_id"), table_name="exam_papers")
    op.drop_index(op.f("ix_exam_papers_created_at"), table_name="exam_papers")
    op.drop_table("exam_papers")


def downgrade() -> None:
    # Recreate the legacy tables verbatim from the initial migration so that
    # a downgrade stays possible even though the flow is retired.
    op.create_table(
        "exam_papers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("question_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_time_spent", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exam_papers_created_at"), "exam_papers", ["created_at"], unique=False)
    op.create_index(op.f("ix_exam_papers_user_id"), "exam_papers", ["user_id"], unique=False)
    op.create_table(
        "exam_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=20), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("time_spent", sa.Integer(), nullable=True),
        sa.Column("hints_used", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
