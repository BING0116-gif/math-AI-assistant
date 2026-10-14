"""add outbox lease ownership for crash recovery and fencing"""
import sqlalchemy as sa
from alembic import op

revision = "ab5f60718294"
down_revision = "ff60718293a4"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("locked_by", sa.String(64), nullable=True))
    op.create_index("ix_outbox_lease_claim", "outbox_events", ["status", "lease_until", "available_at"])

def downgrade() -> None:
    op.drop_index("ix_outbox_lease_claim", table_name="outbox_events")
    op.drop_column("outbox_events", "locked_by")
    op.drop_column("outbox_events", "lease_until")
