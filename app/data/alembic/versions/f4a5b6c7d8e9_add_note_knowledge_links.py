"""add note knowledge links

Revision ID: f4a5b6c7d8e9
Revises: f2a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a5b6c7d8e9"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "note_knowledge_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("study_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("knowledge_point_code_snapshot", sa.String(100), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("ai_run_id", sa.String(36), sa.ForeignKey("note_ai_runs.id", ondelete="SET NULL")),
        sa.Column("confirmed_by_user_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('ai','manual')", name="ck_note_knowledge_link_source"),
        sa.CheckConstraint("status IN ('suggested','confirmed','rejected')", name="ck_note_knowledge_link_status"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_note_knowledge_link_confidence"),
        sa.UniqueConstraint("note_id", "knowledge_point_id", "relation_type", name="uq_note_knowledge_link_target"),
    )
    op.create_index("ix_note_knowledge_link_owner_status", "note_knowledge_links", ["user_id", "status"])
    op.create_index("ix_note_knowledge_link_note", "note_knowledge_links", ["user_id", "note_id"])


def downgrade():
    op.drop_index("ix_note_knowledge_link_note", table_name="note_knowledge_links")
    op.drop_index("ix_note_knowledge_link_owner_status", table_name="note_knowledge_links")
    op.drop_table("note_knowledge_links")
