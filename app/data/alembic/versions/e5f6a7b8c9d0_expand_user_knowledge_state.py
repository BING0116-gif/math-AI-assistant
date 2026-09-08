"""expand canonical user knowledge state

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_knowledge_states") as batch:
        batch.add_column(sa.Column("memory_strength", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("confidence", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("mistake_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("error_type_counts", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("variant_attempts_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("variant_correct_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("variant_performance", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("calculation_version", sa.String(40), nullable=False, server_default="uks-rules-v1"))
        batch.add_column(sa.Column("calculation_reason", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("evolution_history", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("user_knowledge_states") as batch:
        for name in (
            "evolution_history", "calculation_reason", "calculation_version",
            "next_review_at", "last_reviewed_at", "variant_performance",
            "variant_correct_count", "variant_attempts_count", "error_type_counts",
            "mistake_count", "confidence", "memory_strength",
        ):
            batch.drop_column(name)
