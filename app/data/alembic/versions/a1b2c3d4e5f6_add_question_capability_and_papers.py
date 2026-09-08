"""add question capability fields + paper composition tables

P0-7（题型边界 + 组卷能力）：
- questions 新增判题/组卷能力字段，发布时按题型派生：
  grading_mode（deterministic/llm_assisted/manual）、practice_eligible、
  exam_eligible、auto_grading_eligible；组卷只消费 exam_eligible + auto_grading_eligible 的客观题。
- 存量题按 question_type 回填（choice/judge/numeric_fill/expression_fill → 客观题能力）。
- 新增组卷领域表：paper_templates（复用规则模板）、papers（生成产物）、
  paper_questions（卷内题目快照，题库后续编辑/退役不影响已生成试卷）。

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
"""

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None

_OBJECTIVE_TYPES = ("choice", "judge", "numeric_fill", "expression_fill")


def upgrade() -> None:
    # ── questions 能力字段（P0-7）──
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("grading_mode", sa.String(20), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("practice_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("exam_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("auto_grading_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index("ix_questions_auto_grading_eligible", ["auto_grading_eligible"])

    # 存量题按题型回填能力字段（可重复执行）
    op.execute(
        sa.text(
            "UPDATE questions SET "
            "grading_mode = CASE WHEN question_type IN :types THEN 'deterministic' ELSE 'manual' END, "
            "practice_eligible = true, "
            "exam_eligible = CASE WHEN question_type IN :types THEN true ELSE false END, "
            "auto_grading_eligible = CASE WHEN question_type IN :types THEN true ELSE false END"
        ).bindparams(
            sa.bindparam("types", value=list(_OBJECTIVE_TYPES), expanding=True, type_=sa.String())
        )
    )

    # ── 组卷领域表 ──
    op.create_table(
        "paper_templates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=True),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_graph_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_templates_course", "paper_templates", ["course_id"])
    op.create_index("ix_paper_templates_version", "paper_templates", ["version_id"])

    op.create_table(
        "papers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("template_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=True),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["paper_templates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_papers_template", "papers", ["template_id"])
    op.create_index("ix_papers_course", "papers", ["course_id"])
    op.create_index("ix_papers_version", "papers", ["version_id"])
    op.create_index("ix_papers_created_at", "papers", ["created_at"])

    op.create_table(
        "paper_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="10"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_questions_paper", "paper_questions", ["paper_id"])
    op.create_index("ix_paper_questions_question", "paper_questions", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_questions_question", table_name="paper_questions")
    op.drop_index("ix_paper_questions_paper", table_name="paper_questions")
    op.drop_table("paper_questions")

    op.drop_index("ix_papers_created_at", table_name="papers")
    op.drop_index("ix_papers_version", table_name="papers")
    op.drop_index("ix_papers_course", table_name="papers")
    op.drop_index("ix_papers_template", table_name="papers")
    op.drop_table("papers")

    op.drop_index("ix_paper_templates_version", table_name="paper_templates")
    op.drop_index("ix_paper_templates_course", table_name="paper_templates")
    op.drop_table("paper_templates")

    with op.batch_alter_table("questions") as batch:
        batch.drop_index("ix_questions_auto_grading_eligible")
        batch.drop_column("auto_grading_eligible")
        batch.drop_column("exam_eligible")
        batch.drop_column("practice_eligible")
        batch.drop_column("grading_mode")
