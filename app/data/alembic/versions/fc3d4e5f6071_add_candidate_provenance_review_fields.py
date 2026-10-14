"""add candidate source crop and suggested difficulty

Revision ID: fc3d4e5f6071
Revises: fb2c3d4e5f60
"""

from alembic import op
import sqlalchemy as sa


revision = "fc3d4e5f6071"
down_revision = "fb2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("content_import_candidates", sa.Column("source_bbox", sa.JSON(), nullable=True))
    op.add_column("content_import_candidates", sa.Column("suggested_difficulty", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("content_import_candidates", "suggested_difficulty")
    op.drop_column("content_import_candidates", "source_bbox")
