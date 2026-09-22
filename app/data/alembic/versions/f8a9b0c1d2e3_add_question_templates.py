"""Add question_templates table and variant_generations.generation_source.

§5.3 参数化变式题模板（apply-module-refactor-plan-v1）：
- 新表 question_templates：纯确定性参数采样模板，draft/published 状态机人工抽检；
- variant_generations 增加 generation_source（template|llm|hybrid），存量行为
  确定性模板生成，server_default='template' 与现状一致。
只增不改旧表；downgrade 删列删表。

Revision ID: f8a9b0c1d2e3
Revises: e7a8b9c0d1f2
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7a8b9c0d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("base_question_id", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("question_type", sa.String(length=20), nullable=False),
        sa.Column("params_schema", sa.JSON(), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("answer_template", sa.Text(), nullable=False),
        sa.Column("options_template", sa.JSON(), nullable=True),
        sa.Column("knowledge_point_codes", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("generation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_graph_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_question_templates_course_id"), "question_templates", ["course_id"], unique=False)
    op.create_index(op.f("ix_question_templates_version_id"), "question_templates", ["version_id"], unique=False)
    op.create_index(op.f("ix_question_templates_review_status"), "question_templates", ["review_status"], unique=False)
    op.create_index("ix_question_templates_scope_status", "question_templates", ["course_id", "version_id", "review_status"], unique=False)
    op.add_column(
        "variant_generations",
        sa.Column("generation_source", sa.String(length=20), nullable=False, server_default="template"),
    )


def downgrade() -> None:
    op.drop_column("variant_generations", "generation_source")
    op.drop_index("ix_question_templates_scope_status", table_name="question_templates")
    op.drop_index(op.f("ix_question_templates_review_status"), table_name="question_templates")
    op.drop_index(op.f("ix_question_templates_version_id"), table_name="question_templates")
    op.drop_index(op.f("ix_question_templates_course_id"), table_name="question_templates")
    op.drop_table("question_templates")
