"""add owner-scoped note assets

Revision ID: d7e8f9a0b1c2
Revises: f1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("note_assets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("note_id", sa.String(36), sa.ForeignKey("study_notes.id", ondelete="CASCADE"), nullable=False), sa.Column("page_id", sa.String(36), sa.ForeignKey("note_pages.id", ondelete="SET NULL"), nullable=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("storage_key", sa.String(500), nullable=False, unique=True), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("media_type", sa.String(100), nullable=False), sa.Column("size_bytes", sa.BigInteger, nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("asset_kind", sa.String(20), nullable=False, server_default="image"), sa.Column("status", sa.String(20), nullable=False, server_default="active"), sa.Column("cleanup_after", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("asset_kind IN ('image','preview')", name="ck_note_asset_kind"), sa.CheckConstraint("status IN ('active','pending_cleanup')", name="ck_note_asset_status"), sa.CheckConstraint("size_bytes >= 0", name="ck_note_asset_size"), sa.CheckConstraint("length(sha256) = 64", name="ck_note_asset_sha"))
    op.create_index("ix_note_asset_owner_page", "note_assets", ["user_id", "page_id"])

def downgrade():
    op.drop_index("ix_note_asset_owner_page", table_name="note_assets")
    op.drop_table("note_assets")
