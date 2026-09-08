"""add Phase 1 knowledge catalog tables

Revision ID: b4a8c1d2e3f4
Revises: 9d3f2a6b7c81
"""

from alembic import op
import sqlalchemy as sa


revision = "b4a8c1d2e3f4"
down_revision = "9d3f2a6b7c81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("default_version_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_courses_code", "courses", ["code"], unique=True)
    op.create_table(
        "knowledge_graph_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("based_on_version_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("published_by", sa.String(36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "version", name="uq_course_graph_version"),
    )
    op.create_index("ix_knowledge_graph_versions_course_id", "knowledge_graph_versions", ["course_id"])
    op.create_table(
        "chapters",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_graph_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["chapters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "code", name="uq_chapter_version_code"),
    )
    op.create_index("ix_chapters_course_id", "chapters", ["course_id"])
    op.create_index("ix_chapters_version_id", "chapters", ["version_id"])
    op.create_index("ix_chapters_parent_id", "chapters", ["parent_id"])
    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("chapter_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("learning_objectives", sa.JSON(), nullable=False),
        sa.Column("common_errors", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_graph_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "code", name="uq_point_version_code"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_point_difficulty"),
        sa.CheckConstraint("importance BETWEEN 0 AND 1", name="ck_point_importance"),
    )
    op.create_index("ix_knowledge_points_course_id", "knowledge_points", ["course_id"])
    op.create_index("ix_knowledge_points_version_id", "knowledge_points", ["version_id"])
    op.create_index("ix_knowledge_points_chapter_id", "knowledge_points", ["chapter_id"])
    op.create_index("idx_point_version_chapter_order", "knowledge_points", ["version_id", "chapter_id", "sort_order"])


def downgrade() -> None:
    op.drop_index("idx_point_version_chapter_order", table_name="knowledge_points")
    op.drop_index("ix_knowledge_points_chapter_id", table_name="knowledge_points")
    op.drop_index("ix_knowledge_points_version_id", table_name="knowledge_points")
    op.drop_index("ix_knowledge_points_course_id", table_name="knowledge_points")
    op.drop_table("knowledge_points")
    op.drop_index("ix_chapters_parent_id", table_name="chapters")
    op.drop_index("ix_chapters_version_id", table_name="chapters")
    op.drop_index("ix_chapters_course_id", table_name="chapters")
    op.drop_table("chapters")
    op.drop_index("ix_knowledge_graph_versions_course_id", table_name="knowledge_graph_versions")
    op.drop_table("knowledge_graph_versions")
    op.drop_index("ix_courses_code", table_name="courses")
    op.drop_table("courses")
