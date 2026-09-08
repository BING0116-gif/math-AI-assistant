"""add content operations metadata, revisions and feedback

Revision ID: ad4e5f607182
Revises: ac3d4e5f6071
"""
import sqlalchemy as sa
from alembic import op

revision = "ad4e5f607182"
down_revision = "ac3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("source_name", sa.String(255), nullable=True))
    op.add_column("source_documents", sa.Column("license_type", sa.String(50), nullable=True))
    op.add_column("source_documents", sa.Column("license_note", sa.Text(), nullable=True))
    op.add_column("source_documents", sa.Column("license_evidence_ref", sa.String(500), nullable=True))
    op.add_column("source_documents", sa.Column("license_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_source_documents_license_type", "source_documents", ["license_type"])
    op.create_table(
        "question_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.String(36), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", "version", name="uq_question_revision_version"),
    )
    op.create_index("ix_question_revision_question_created", "question_revisions", ["question_id", "created_at"])
    op.create_table(
        "question_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("issue_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("submitted_by", sa.String(36), nullable=False),
        sa.Column("resolved_by", sa.String(36), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_question_feedback_issue_type", "question_feedback", ["issue_type"])
    op.create_index("ix_question_feedback_status", "question_feedback", ["status"])
    op.create_index("ix_question_feedback_question_status", "question_feedback", ["question_id", "status"])


def downgrade() -> None:
    op.drop_table("question_feedback")
    op.drop_table("question_revisions")
    op.drop_index("ix_source_documents_license_type", table_name="source_documents")
    for name in ("license_confirmed_at", "license_evidence_ref", "license_note", "license_type", "source_name"):
        op.drop_column("source_documents", name)
