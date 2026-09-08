"""add durable outbox events

Revision ID: ae5f60718293
Revises: ad4e5f607182
"""
import sqlalchemy as sa
from alembic import op

revision = "ae5f60718293"
down_revision = "ad4e5f607182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
    )
    op.create_index("ix_outbox_status_available", "outbox_events", ["status", "available_at"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])
    op.create_index("ix_outbox_user", "outbox_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("outbox_events")
