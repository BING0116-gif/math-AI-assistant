"""add auditable learning activity and legacy import

Revision ID: ab2c3d4e5f60
Revises: aa1b2c3d4e5f
"""
import sqlalchemy as sa
from alembic import op

revision = "ab2c3d4e5f60"
down_revision = "aa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_activity_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("client_session_id", sa.String(128), nullable=False),
        sa.Column("context_type", sa.String(30), nullable=False),
        sa.Column("context_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "client_session_id", name="uq_learning_activity_owner_client"),
    )
    op.create_index("ix_learning_activity_owner_started", "learning_activity_sessions", ["user_id", "started_at"])
    op.create_index("ix_learning_activity_owner_status", "learning_activity_sessions", ["user_id", "status"])
    op.create_table(
        "legacy_client_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("imported_chats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "batch_id", name="uq_legacy_import_owner_batch"),
    )
    op.create_index("ix_legacy_import_owner_created", "legacy_client_imports", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_legacy_import_owner_created", table_name="legacy_client_imports")
    op.drop_table("legacy_client_imports")
    op.drop_index("ix_learning_activity_owner_status", table_name="learning_activity_sessions")
    op.drop_index("ix_learning_activity_owner_started", table_name="learning_activity_sessions")
    op.drop_table("learning_activity_sessions")
