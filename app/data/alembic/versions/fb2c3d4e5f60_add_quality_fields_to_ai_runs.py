"""add quality-loop fields to ai interaction runs

Revision ID: fb2c3d4e5f60
Revises: f9a0b1c2d3e4
"""

from alembic import op
import sqlalchemy as sa


revision = "fb2c3d4e5f60"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_interaction_runs", sa.Column("critic_verdict", sa.String(length=10), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("critic_issues", sa.JSON(), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("quality_sampled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("ai_interaction_runs", sa.Column("review_verdict", sa.String(length=10), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("reviewer_id", sa.String(length=36), nullable=True))
    op.add_column("ai_interaction_runs", sa.Column("followup_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_interaction_runs", sa.Column("modified_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade():
    for name in ("modified_by_user", "followup_count", "reviewer_id", "review_verdict", "quality_sampled", "critic_issues", "critic_verdict"):
        op.drop_column("ai_interaction_runs", name)

