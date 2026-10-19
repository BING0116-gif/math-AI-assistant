"""Phase 4 Task 4.2 append-only mastery correction reports."""
from alembic import op
import sqlalchemy as sa

revision = "gh60718293a6"
down_revision = "fg60718293a5"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "mastery_correction_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_point_code", sa.String(100), nullable=False),
        sa.Column("correction_type", sa.String(30), nullable=False),
        sa.Column("original_value", sa.String(200), nullable=True),
        sa.Column("proposed_value", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("correction_type IN ('error_type','knowledge_point')", name="ck_mastery_correction_type"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_mastery_correction_owner_idem"),
    )
    op.create_index("ix_mastery_correction_owner_point", "mastery_correction_events", ["user_id", "knowledge_point_code", "created_at"])

def downgrade():
    op.drop_table("mastery_correction_events")
