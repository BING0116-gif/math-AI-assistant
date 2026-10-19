"""add proactive learning action audit and preferences"""
from alembic import op
import sqlalchemy as sa
revision = "lm60718293aa"
down_revision = "kl60718293a9"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("learning_automation_preferences",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allowed_channel", sa.String(20), nullable=False, server_default="in_app"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("proactive_learning_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False), sa.Column("trigger", sa.String(60), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("frequency_key", sa.String(200), nullable=False),
        sa.Column("cooldown_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("result", sa.JSON()), sa.Column("last_error", sa.Text()), sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "frequency_key", name="uq_proactive_action_frequency"),
        sa.CheckConstraint("status IN ('pending','delivered','failed','dead','cancelled','expired')", name="ck_proactive_action_status"))
    op.create_index("ix_proactive_actions_user_status", "proactive_learning_actions", ["user_id", "status"])
    op.create_index("ix_proactive_actions_expiry", "proactive_learning_actions", ["expires_at", "status"])
def downgrade():
    op.drop_table("proactive_learning_actions")
    op.drop_table("learning_automation_preferences")
