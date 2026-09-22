"""§5.3 参数化变式题模板回归测试。

覆盖：参数 schema 校验与确定性采样、{{param}} 渲染、sympy 答案固化（复用判分契约）、
试生成抽检、draft→published 状态机、指纹去重、组卷候选池合并（PaperGenerator 与
智能组卷 _select_questions 的题荒补齐）、迁移空库全链升级。
"""
import random
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, Question,
    QuestionKnowledgePoint, QuestionTemplate, User,
)
from app.services.paper_generator import PaperGenerator, _grade_one
from app.services.question_template_service import (
    QuestionTemplateError, build_answer_spec, create_template, get_template,
    list_templates, materialize_pool, params_fingerprint, render_one_instance,
    render_template, sample_params, sample_preview, set_template_status,
    validate_params_schema,
)


async def _seed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            Course(id="course-1", code="calculus", name="高等数学", subject="math", default_version_id="version-1"),
            KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published"),
            Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="函数"),
            KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限"),
            KnowledgePoint(id="point-2", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="deriv", name="导数"),
            User(id="admin-1", username="admin", email="admin@example.test", password_hash="x", role="admin"),
        ])
        await db.flush()
        for index in range(4):
            question = Question(
                id=f"Q-{index}", content=f"{index}+1=?", question_type="numeric_fill",
                answer=str(index + 1), category="高数", difficulty=2,
                course_id="course-1", version_id="version-1",
                review_status="published", grading_mode="deterministic",
                practice_eligible=True, exam_eligible=True, auto_grading_eligible=True,
                answer_spec={"version": 1, "kind": "numeric_fill", "value": index + 1},
            )
            db.add(question); await db.flush()
            db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()
    return engine, factory


TEMPLATE_PAYLOAD = {
    "course_id": "course-1", "version_id": "version-1",
    "name": "导数乘法公式", "question_type": "numeric_fill",
    "params_schema": {"a": {"type": "int", "range": [1, 9]}, "b": {"type": "int", "range": [1, 9]}},
    "body_template": "计算 ${{a}} \\times {{b}}$",
    "answer_template": "{{a}}*{{b}}",
    "knowledge_point_codes": ["deriv"],
    "difficulty": 2,
}


# ── 纯函数层 ──
def test_params_schema_validation_and_sampling():
    schema = validate_params_schema({"a": {"type": "int", "range": [1, 9]}, "op": {"type": "enum", "values": ["+", "-"]}, "x": {"type": "float", "range": [0.5, 2.5], "precision": 1}})
    first = sample_params(schema, random.Random(42))
    second = sample_params(schema, random.Random(42))
    assert first == second
    assert 1 <= first["a"] <= 9 and first["op"] in "+-" and 0.5 <= first["x"] <= 2.5
    with pytest.raises(QuestionTemplateError, match="参数"):
        validate_params_schema({"bad": {"type": " gauss"}})
    with pytest.raises(QuestionTemplateError, match="范围"):
        validate_params_schema({"a": {"type": "int", "range": [9, 1]}})


def test_render_template_replaces_placeholders():
    assert render_template("{{a}}+{{b}}", {"a": 3, "b": 4}) == "3+4"
    with pytest.raises(QuestionTemplateError, match="未知占位符"):
        render_template("{{a}}+{{c}}", {"a": 3})


def test_build_answer_spec_uses_grading_contract():
    numeric = build_answer_spec("numeric_fill", "3*4")
    assert numeric == {"version": 1, "kind": "numeric_fill", "value": 12}
    expression = build_answer_spec("expression_fill", "2*x+1", variables=["x"])
    assert expression["kind"] == "expression_fill" and expression["variables"] == ["x"]
    choice = build_answer_spec("choice", "A")
    assert choice["correct"] == "A"
    judge = build_answer_spec("judge", "true")
    assert judge["correct"] is True
    with pytest.raises(QuestionTemplateError, match="无法求值"):
        build_answer_spec("numeric_fill", "___bad___")


def test_render_one_instance_and_grade_by_existing_engine():
    template = QuestionTemplate(
        id="tpl-1", course_id="course-1", version_id="version-1", name="t",
        question_type="numeric_fill",
        params_schema={"a": {"type": "int", "range": [1, 9]}, "b": {"type": "int", "range": [1, 9]}},
        body_template="{{a}}*{{b}}=?", answer_template="{{a}}*{{b}}",
        knowledge_point_codes=["deriv"], difficulty=2, review_status="draft", created_by="admin-1",
    )
    instance = render_one_instance(template, {"a": 6, "b": 7})
    assert instance["body"] == "6*7=?"
    assert instance["answer_spec"]["value"] == 42
    # 判分走现有 _grade_one：对 42 判对，对 41 判错
    assert _grade_one({"answer_spec": instance["answer_spec"]}, "42")["correct"] is True
    assert _grade_one({"answer_spec": instance["answer_spec"]}, "41")["correct"] is False
    assert instance["fingerprint"] == params_fingerprint("tpl-1", {"a": 6, "b": 7})


# ── 服务层（CRUD / 状态机 / 试生成）──
@pytest.mark.asyncio
async def test_template_lifecycle_and_preview(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    created = await create_template("admin-1", TEMPLATE_PAYLOAD)
    assert created.review_status == "draft"
    previews = sample_preview(created, count=10)
    assert len(previews) == 10
    fingerprints = {p["fingerprint"] for p in previews}
    assert len(fingerprints) == 10
    # seed 可复现
    assert [p["params"] for p in sample_preview(created, count=5, seed=7)] == [p["params"] for p in sample_preview(created, count=5, seed=7)]
    published = await set_template_status(created.id, "publish")
    assert published.review_status == "published"
    retired = await set_template_status(created.id, "retire")
    assert retired.review_status == "retired"
    with pytest.raises(QuestionTemplateError, match="发布"):
        await set_template_status(created.id, "publish")
    assert (await get_template(created.id)).id == created.id
    assert len(await list_templates(status="retired")) == 1
    with pytest.raises(QuestionTemplateError, match="知识点"):
        await create_template("admin-1", {**TEMPLATE_PAYLOAD, "knowledge_point_codes": ["nope"]})
    await engine.dispose()


@pytest.mark.asyncio
async def test_materialize_pool_deduplicates_and_links_knowledge_points(monkeypatch):
    engine, factory = await _seed(monkeypatch)
    created = await create_template("admin-1", TEMPLATE_PAYLOAD)
    await set_template_status(created.id, "publish")
    first = await materialize_pool("course-1", "version-1", ["numeric_fill"], ["deriv"], seed=100)
    assert first and all(q.review_status == "published" for q in first)
    assert all(q.source == f"template:{created.id}" for q in first)
    assert all(q.grading_mode == "deterministic" and q.exam_eligible for q in first)
    # 第二次实例化生成"新的"参数组合（rng 种子含已用指纹数），且与第一批不重复
    second = await materialize_pool("course-1", "version-1", ["numeric_fill"], ["deriv"], seed=100)
    first_prints = {q.variant_blueprint["fingerprint"] for q in first}
    second_prints = {q.variant_blueprint["fingerprint"] for q in second}
    assert second and first_prints.isdisjoint(second_prints)
    # 下架后不再实例化
    await set_template_status(created.id, "retire")
    assert await materialize_pool("course-1", "version-1", ["numeric_fill"], ["deriv"], seed=1) == []
    async with factory() as db:
        rows = list((await db.execute(select(Question).where(Question.source == f"template:{created.id}"))).scalars())
        assert len(rows) == len(first) + len(second)
    await engine.dispose()


@pytest.mark.asyncio
async def test_materialize_pool_fingerprint_dedup(monkeypatch):
    engine, factory = await _seed(monkeypatch)
    created = await create_template("admin-1", {**TEMPLATE_PAYLOAD, "params_schema": {"a": {"type": "int", "range": [2, 2]}, "b": {"type": "int", "range": [3, 3]}}})
    await set_template_status(created.id, "publish")
    first = await materialize_pool("course-1", "version-1", ["numeric_fill"], ["deriv"], seed=5)
    # 参数空间只有一种组合：第一次实例化 1 题，后续因指纹重复不再生成
    assert len(first) == 1
    second = await materialize_pool("course-1", "version-1", ["numeric_fill"], ["deriv"], seed=9)
    assert second == []
    async with factory() as db:
        rows = list((await db.execute(select(Question).where(Question.source == f"template:{created.id}"))).scalars())
        assert len(rows) == 1
        assert rows[0].variant_blueprint["params"] == {"a": 2, "b": 3}
    await engine.dispose()


# ── 组卷接入：PaperGenerator 池合并 ──
@pytest.mark.asyncio
async def test_paper_generator_merges_template_questions(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    # 模板覆盖 limit：正式题库 limit 只有 4 题，配额 7 由模板实例化题补齐
    created = await create_template("admin-1", {**TEMPLATE_PAYLOAD, "knowledge_point_codes": ["limit"]})
    await set_template_status(created.id, "publish")
    gen = PaperGenerator()
    paper = await gen.generate(config={
        "title": "模板题补齐卷", "course_id": "course-1", "version_id": "version-1",
        "kp_codes": ["limit"], "type_mix": {"numeric_fill": 7},
        "total_score": 10, "random_seed": 11,
    })
    contents = [(pq.snapshot or {}).get("content") for pq in paper.questions]
    assert len(contents) == 7
    template_generated = [pq for pq in paper.questions if str(pq.question_id).startswith("qt-")]
    assert len(template_generated) == 3, "模板实例化题应补齐题荒配额"
    await engine.dispose()


# ── 迁移：空库全链升级到 head（含新迁移）──
def test_migration_chain_upgrades_clean_sqlite():
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "app" / "data" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "app" / "data" / "alembic"))
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_url = f"sqlite:///{tmp}/migration_chain.db".replace("\\", "/")
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "f8a9b0c1d2e3-1")
        command.upgrade(cfg, "head")
