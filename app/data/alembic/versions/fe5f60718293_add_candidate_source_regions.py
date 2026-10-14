"""add multi-page candidate source regions

Revision ID: fe5f60718293
Revises: fd4e5f607182
"""

from alembic import op
import sqlalchemy as sa


revision = "fe5f60718293"
down_revision = "fd4e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("content_import_candidates", sa.Column("source_regions", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("content_import_candidates", "source_regions")
