"""add owner-scoped handwritten notes

Revision ID: fa1b2c3d4e5f
Revises: f9a0b1c2d3e4
"""
from alembic import op
import sqlalchemy as sa

revision = "fa1b2c3d4e5f"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("note_type", sa.String(20), nullable=False, server_default="handwritten"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("note_type = 'handwritten'", name="ck_study_note_type"),
        sa.CheckConstraint("status IN ('active','deleted')", name="ck_study_note_status"),
    )
    op.create_index("ix_study_note_owner_updated", "study_notes", ["user_id", "updated_at"])
    op.create_index("ix_study_note_owner_status", "study_notes", ["user_id", "status"])
    op.create_table(
        "note_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("study_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("background_type", sa.String(20), nullable=False, server_default="dot"),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("page_number > 0 AND width > 0 AND height > 0", name="ck_note_page_dimensions"),
        sa.CheckConstraint("background_type IN ('blank','lined','grid','dot')", name="ck_note_page_background"),
        sa.UniqueConstraint("note_id", "page_number", name="uq_note_page_number"),
    )
    op.create_index("ix_note_page_owner_note", "note_pages", ["user_id", "note_id"])
    op.create_table(
        "note_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("page_id", sa.String(36), sa.ForeignKey("note_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("stroke_storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_number > 0 AND base_revision >= 0 AND size_bytes >= 0", name="ck_note_revision_values"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_note_revision_sha"),
        sa.UniqueConstraint("page_id", "revision_number", name="uq_note_revision_number"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_note_revision_owner_idem"),
    )
    op.create_index("ix_note_revision_owner_page", "note_revisions", ["user_id", "page_id"])


def downgrade():
    op.drop_table("note_revisions")
    op.drop_table("note_pages")
    op.drop_table("study_notes")
