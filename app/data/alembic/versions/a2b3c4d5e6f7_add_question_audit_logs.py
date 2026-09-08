"""add question_audit_logs

P0-8：正式题目状态审计表。每次审核/发布等状态变化写入一条事件
（question_id / action / from_status / to_status / operator_id / reason / details），
补齐发布治理的最后一块：Gate 强制 + 旧入口封禁 + 状态变化留痕。

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
"""

import sqlalchemy as sa

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("operator_id", sa.String(36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_question_audit_logs_question_id", "question_audit_logs", ["question_id"])
    op.create_index("ix_question_audit_logs_created_at", "question_audit_logs", ["created_at"])
    op.create_index(
        "ix_qa_question_created", "question_audit_logs", ["question_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_qa_question_created", table_name="question_audit_logs")
    op.drop_index("ix_question_audit_logs_created_at", table_name="question_audit_logs")
    op.drop_index("ix_question_audit_logs_question_id", table_name="question_audit_logs")
    op.drop_table("question_audit_logs")
