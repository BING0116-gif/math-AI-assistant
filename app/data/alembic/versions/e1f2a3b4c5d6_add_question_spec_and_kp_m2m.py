"""add question review/spec fields and question-knowledgepoint M2M

Step 1.1: freeze calculus knowledge system and question specification.
- courses / knowledge_graph_versions already exist (b4a8c1d2e3f4).
- adds: knowledge_points.prerequisites + related
- adds: questions.course_id / version_id / review_status / is_ai_generated /
  common_mistakes / answer_spec
- adds: question_knowledge_points (normalized M:N)
- data migration: existing questions -> review_status='draft';
  best-effort map legacy knowledge_points string names to points.

Revision ID: e1f2a3b4c5d6
Revises: d6e0f3a4b5c6
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d6e0f3a4b5c6"
branch_labels = None
depends_on = None


def _parse_kp_names(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, TypeError):
        pass
    # fallback: comma separated
    return [part.strip() for part in value.split(",") if part.strip()]


def upgrade() -> None:
    bind = op.get_bind()

    # ── knowledge_points: prerequisites / related ──
    with op.batch_alter_table("knowledge_points") as batch:
        batch.add_column(sa.Column("prerequisites", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("related", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    # ── questions: new columns ──
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("course_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False, server_default="draft"))
        batch.add_column(sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("common_mistakes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("answer_spec", sa.JSON(), nullable=True))
        batch.create_index("ix_questions_review_status", ["review_status"])
        batch.create_index("ix_questions_course_id", ["course_id"])
        batch.create_index("ix_questions_version_id", ["version_id"])
        batch.create_foreign_key("fk_questions_course_id", "courses", ["course_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_questions_version_id", "knowledge_graph_versions", ["version_id"], ["id"], ondelete="RESTRICT")

    # ── question_knowledge_points (normalized M:N) ──
    op.create_table(
        "question_knowledge_points",
        sa.Column("question_id", sa.String(20), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "knowledge_point_id"),
    )
    op.create_index("ix_qkp_knowledge_point", "question_knowledge_points", ["knowledge_point_id"])

    # ── data migration: legacy knowledge_points string -> M:N (best effort) ──
    # Match legacy Chinese display names against existing knowledge_point.name.
    # Existing bank is derivative-chapter (out of scope) so realistically 0 links;
    # this is intentionally non-destructive and leaves questions as draft.
    #
    # 注意：PostgreSQL DDL 是事务性的，question_knowledge_points 表刚创建、尚未提交。
    # 必须使用迁移事务内的 bind（op.get_bind()）执行，不能 bind.connect() 开独立连接，
    # 否则新连接看不到未提交的表，INSERT 会失败（被 except 吞掉 → 0 关联）。
    try:
        point_rows = bind.execute(sa.text(
            "SELECT id, name FROM knowledge_points"
        )).fetchall()
        name_to_id = {name: pid for pid, name in point_rows if name}
        q_rows = bind.execute(sa.text(
            "SELECT id, knowledge_points FROM questions"
        )).fetchall()
        link_rows = []
        for qid, kp_str in q_rows:
            for name in _parse_kp_names(kp_str):
                kp_id = name_to_id.get(name)
                if kp_id:
                    link_rows.append((qid, kp_id))
        if link_rows:
            # 方言无关的幂等插入：仅插入尚不存在的关联
            for qid, kpid in link_rows:
                bind.execute(
                    sa.text(
                        "INSERT INTO question_knowledge_points (question_id, knowledge_point_id, is_primary) "
                        "SELECT :q, :k, false WHERE NOT EXISTS ("
                        "  SELECT 1 FROM question_knowledge_points "
                        "  WHERE question_id = :q AND knowledge_point_id = :k)"
                    ),
                    {"q": qid, "k": kpid},
                )
    except Exception as e:  # noqa: BLE001
        import sys
        print(f"[m2m data migration] skipped: {type(e).__name__}: {e}", file=sys.stderr)
        # migration must not hard-fail on best-effort data linking
        pass


def downgrade() -> None:
    op.drop_index("ix_qkp_knowledge_point", table_name="question_knowledge_points")
    op.drop_table("question_knowledge_points")

    with op.batch_alter_table("questions") as batch:
        batch.drop_constraint("fk_questions_course_id", type_="foreignkey")
        batch.drop_constraint("fk_questions_version_id", type_="foreignkey")
        batch.drop_index("ix_questions_review_status")
        batch.drop_index("ix_questions_course_id")
        batch.drop_index("ix_questions_version_id")
        batch.drop_column("answer_spec")
        batch.drop_column("common_mistakes")
        batch.drop_column("is_ai_generated")
        batch.drop_column("review_status")
        batch.drop_column("version_id")
        batch.drop_column("course_id")

    with op.batch_alter_table("knowledge_points") as batch:
        batch.drop_column("related")
        batch.drop_column("prerequisites")