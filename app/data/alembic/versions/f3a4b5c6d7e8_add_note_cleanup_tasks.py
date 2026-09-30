"""add durable note cleanup tasks

Revision ID: f3a4b5c6d7e8
Revises: d7e8f9a0b1c2
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("note_cleanup_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_keys", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending','processing','completed')", name="ck_note_cleanup_task_status"),
    )
    op.create_index("ix_note_cleanup_task_status_created", "note_cleanup_tasks", ["status", "created_at"])

def downgrade():
    op.drop_index("ix_note_cleanup_task_status_created", table_name="note_cleanup_tasks")
    op.drop_table("note_cleanup_tasks")
