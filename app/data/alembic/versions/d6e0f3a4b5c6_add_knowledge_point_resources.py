"""add extensible knowledge point learning resources

Revision ID: d6e0f3a4b5c6
Revises: c5d9e2f3a4b5
"""

from alembic import op
import sqlalchemy as sa

revision = "d6e0f3a4b5c6"
down_revision = "c5d9e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_point_resources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_point_id", "resource_type", "title", name="uq_point_resource_type_title"),
    )
    op.create_index("ix_knowledge_point_resources_knowledge_point_id", "knowledge_point_resources", ["knowledge_point_id"])
    op.create_index("ix_knowledge_point_resources_resource_type", "knowledge_point_resources", ["resource_type"])
    op.create_index("idx_point_resource_order", "knowledge_point_resources", ["knowledge_point_id", "resource_type", "sort_order"])


def downgrade() -> None:
    op.drop_index("idx_point_resource_order", table_name="knowledge_point_resources")
    op.drop_index("ix_knowledge_point_resources_resource_type", table_name="knowledge_point_resources")
    op.drop_index("ix_knowledge_point_resources_knowledge_point_id", table_name="knowledge_point_resources")
    op.drop_table("knowledge_point_resources")
