"""add note AI runs

Revision ID: f2a3b4c5d6e7
Revises: f3a4b5c6d7e8
"""
from alembic import op
import sqlalchemy as sa
revision="f2a3b4c5d6e7"; down_revision="f3a4b5c6d7e8"; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("note_ai_runs",sa.Column("id",sa.String(36),primary_key=True),sa.Column("note_id",sa.String(36),sa.ForeignKey("study_notes.id",ondelete="CASCADE"),nullable=False),sa.Column("page_id",sa.String(36),sa.ForeignKey("note_pages.id",ondelete="CASCADE"),nullable=False),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("source_revision",sa.Integer,nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("model",sa.String(100),nullable=False),sa.Column("prompt_version",sa.String(40),nullable=False),sa.Column("result",sa.JSON),sa.Column("error",sa.String(500)),sa.Column("attempt_no",sa.Integer,nullable=False),sa.Column("idempotency_key",sa.String(128),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.CheckConstraint("status IN ('pending','running','needs_review','failed')",name="ck_note_ai_run_status"),sa.UniqueConstraint("user_id","idempotency_key",name="uq_note_ai_run_owner_idem"))
 op.create_index("ix_note_ai_run_page_revision","note_ai_runs",["page_id","source_revision"])
def downgrade(): op.drop_index("ix_note_ai_run_page_revision",table_name="note_ai_runs");op.drop_table("note_ai_runs")
