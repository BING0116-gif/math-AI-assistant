"""Add rebuildable chat context checkpoints."""
from alembic import op
import sqlalchemy as sa

revision = "no60718293ac"
down_revision = "mn60718293ab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_context_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("covered_through_message_id", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", name="uq_chat_context_checkpoint_session"),
    )
    op.create_index("ix_chat_context_checkpoints_user_id", "chat_context_checkpoints", ["user_id"])


def downgrade():
    op.drop_index("ix_chat_context_checkpoints_user_id", table_name="chat_context_checkpoints")
    op.drop_table("chat_context_checkpoints")
