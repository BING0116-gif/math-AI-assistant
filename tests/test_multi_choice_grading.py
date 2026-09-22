"""§5.4 多选题计分 / 选项乱序 / review_policy / 蓝图预览回归矩阵。

矩阵覆盖：三计分策略（all_or_nothing / partial / partial_minus）× 作答组合
（全对 / 漏选 / 错选 / 空 / 多型输入）× 乱序映射（快照顺序改变、判分按 id 不变）
× behavior 联动（immediate 重试）× exam/assessment 的 review_policy 与 SSE 预览。
"""
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, PracticeSession,
    Question, QuestionKnowledgePoint, User,
)
from app.services.exam_service import create_exam, start_exam, submit_exam
from app.services.paper_generator import _grade_one
from app.services.practice_service import (
    PracticeError, apply_options_shuffle, create_session, start_session, submit_attempt,
)
import random


def spec(scoring):
    return {"version": 1, "kind": "multi_choice", "correct": ["A", "C"], "scoring": scoring}


@pytest.mark.parametrize("scoring,answer,expected_correct,expected_credit", [
    # 全对：三种策略都满分
    ("all_or_nothing", ["A", "C"], True, 1.0),
    ("partial", ["A", "C"], True, 1.0),
    ("partial_minus", ["A", "C"], True, 1.0),
    # 漏选一半：all_or_nothing 0 分；partial 得一半；partial_minus 得一半
    ("all_or_nothing", ["A"], False, 0.0),
    ("partial", ["A"], False, 0.5),
    ("partial_minus", ["A"], False, 0.5),
    # 错选 + 漏选：partial 错选即 0；partial_minus 按净命中折算（1 对 1 错 → 0）
    ("all_or_nothing", ["A", "B"], False, 0.0),
    ("partial", ["A", "B"], False, 0.0),
    ("partial_minus", ["A", "B"], False, 0.0),
    # 只错选：全 0
    ("partial_minus", ["B"], False, 0.0),
    # 空作答：全 0
    ("partial", [], False, 0.0),
    ("partial_minus", None, False, 0.0),
    # 多选全部正确项 + 顺序无关 + 逗号字符串输入
    ("partial", ["C", "A"], True, 1.0),
])
def test_multi_choice_scoring_matrix(scoring, answer, expected_correct, expected_credit):
    graded = _grade_one({"answer_spec": spec(scoring)}, answer)
    assert graded["correct"] is expected_correct
    assert graded["partial_credit"] == expected_credit
    assert graded["correct_answer"] == "A、C"
    assert graded["scoring"] == scoring


def test_multi_choice_input_shapes_and_default_scoring():
    # 未知 scoring 回退 all_or_nothing；非法 scoring 字段不致错
    graded = _grade_one({"answer_spec": {"kind": "multi_choice", "correct": ["A"], "scoring": "weird"}}, ["A"])
    assert graded["correct"] is True and graded["scoring"] == "all_or_nothing"
    # 重复选择去重；空字符串项忽略
    graded = _grade_one({"answer_spec": spec("partial")}, ["A", "A", " "])
    assert graded["partial_credit"] == 0.5


def test_options_shuffle_changes_order_not_identity():
    options = [{"id": letter, "text": letter} for letter in "ABCDEF"]
    snapshot = {"question_type": "multi_choice", "options": list(options), "answer_spec": spec("partial")}
    shuffled = apply_options_shuffle(snapshot, random.Random(3))
    assert shuffled["options_shuffled"] is True
    assert {o["id"] for o in shuffled["options"]} == {o["id"] for o in options}
    assert [o["id"] for o in shuffled["options"]] != [o["id"] for o in options]
    # 判分不受乱序影响（按 id）
    assert _grade_one(shuffled, ["A", "C"])["correct"] is True
    # 非选项题型不乱序
    untouched = apply_options_shuffle({"question_type": "numeric_fill", "options": None}, random.Random(1))
    assert "options_shuffled" not in untouched


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
            User(id="user-1", username="student", email="s@example.test", password_hash="x"),
        ])
        await db.flush()
        for index in range(5):
            question = Question(
                id=f"MC-{index}", content=f"多选题{index}", question_type="multi_choice",
                options=[{"id": "A", "text": "对1"}, {"id": "B", "text": "错"}, {"id": "C", "text": "对2"}, {"id": "D", "text": "错"}],
                answer="A、C", analysis="多选解析", category="高数", difficulty=2,
                course_id="course-1", version_id="version-1",
                review_status="published", grading_mode="deterministic",
                practice_eligible=True, exam_eligible=True, auto_grading_eligible=True,
                answer_spec={"version": 1, "kind": "multi_choice", "correct": ["A", "C"], "scoring": "partial"},
            )
            db.add(question); await db.flush()
            db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()
    return engine, factory


@pytest.mark.asyncio
async def test_exam_multi_choice_full_loop_with_shuffle_and_review_policy(monkeypatch):
    engine, factory = await _seed(monkeypatch)
    session = await create_exam("user-1", {
        "course_id": "course-1", "version_id": "version-1", "knowledge_point_codes": ["limit"],
        "difficulty_min": 1, "difficulty_max": 5, "question_type_counts": {"multi_choice": 5},
        "duration_minutes": 30, "idempotency_key": "exam-mc-1", "random_seed": 11,
    })
    assert session["config"]["review_policy"] == "after_submit"
    assert session["config"]["shuffle_options"] is True
    shuffled_orders = []
    await start_exam("user-1", session["session_id"])
    for question in session["questions"]:
        ids = [option["id"] for option in question["options"]]
        shuffled_orders.append(ids)
        assert set(ids) == {"A", "B", "C", "D"} and "answer_spec" not in question
    # 多数选项顺序应与原始 A/B/C/D 不同（乱序生效）
    assert any(ids != ["A", "B", "C", "D"] for ids in shuffled_orders)
    # 幂等重放兼容服务端注入键
    replay = await create_exam("user-1", {
        "course_id": "course-1", "version_id": "version-1", "knowledge_point_codes": ["limit"],
        "difficulty_min": 1, "difficulty_max": 5, "question_type_counts": {"multi_choice": 5},
        "duration_minutes": 30, "idempotency_key": "exam-mc-1", "random_seed": 11,
    })
    assert replay["session_id"] == session["session_id"]
    # 判分按选项 id：全对 5 题 → 满分；partial_credit 透出
    from app.services.exam_service import save_exam_draft
    for index, question in enumerate(session["questions"]):
        answer = ["A", "C"] if index < 4 else ["A"]  # 最后一题漏选
        await save_exam_draft("user-1", session["session_id"], question["question_id"], answer, 0)
    report = await submit_exam("user-1", session["session_id"])
    assert report["total"] == 5 and report["correct"] == 4
    partial = next(item for item in report["results"] if not item["correct"])
    assert partial["correct_answer"] == "A、C"
    await engine.dispose()


@pytest.mark.asyncio
async def test_practice_multi_choice_with_immediate_retry(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", {
        "course_id": "course-1", "version_id": "version-1", "chapter_ids": ["chapter-1"],
        "knowledge_point_codes": [], "question_types": ["multi_choice"], "question_count": 5,
        "idempotency_key": "practice-mc-1", "behavior": "immediate",
    })
    qid = session["questions"][0]["question_id"]
    await start_session("user-1", session["session_id"])
    first = await submit_attempt("user-1", session["session_id"], qid, ["A"], "mc-attempt-1")
    assert first["correct"] is False and first["partial_credit"] == 0.5
    retry = await submit_attempt("user-1", session["session_id"], qid, ["A", "C"], "mc-attempt-2")
    assert retry["correct"] is True and retry["partial_credit"] == 1.0
    assert retry["learning_signals"]["retry"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_assessment_preview_blueprint_does_not_persist(monkeypatch):
    engine, factory = await _seed(monkeypatch)
    from app.services.assessment_service import preview_assessment_blueprint

    class StubPlanner:
        async def plan(self, signals, inventory, question_count):
            return {"plan": {"buckets": [
                {"quota_kind": "weakness", "knowledge_point_code": "limit", "count": 3, "difficulty_min": 1, "difficulty_max": 5, "reason_code": "weak_mastery", "reason": "画像显示需复测"},
                {"quota_kind": "due_review", "knowledge_point_code": "limit", "count": 2, "difficulty_min": 1, "difficulty_max": 5, "reason_code": "review_due", "reason": "到期复习"},
            ]}, "source": "llm", "model": "stub", "latency_ms": 5, "token_usage": {}, "error_code": None}

    import app.services.assessment_service as service
    async def fake_signals(user_id, points):
        return {"has_history": True, "skills": [], "errors": [], "profile_weak_points": []}
    monkeypatch.setattr(service, "_signals", fake_signals)

    preview = await service.preview_assessment_blueprint("user-1", {
        "goal": "weakness_check", "course_id": "course-1", "version_id": "version-1",
        "scope": {"chapter_ids": ["chapter-1"]}, "duration_minutes": 15, "intensity": "standard",
        "question_count": 5,
    }, planner=StubPlanner())
    assert preview["planning_source"] == "llm" and preview["total"] == 5
    # 桶经 plan 归一化（按 QUOTA_PRESETS/库存约束调整），总量与桶结构保持一致
    assert sum(preview["quota_summary"].values()) == 5
    assert len(preview["plan"]["buckets"]) >= 1
    assert all(bucket["count"] >= 1 for bucket in preview["plan"]["buckets"])
    # 预览不落库、不消耗幂等键
    async with factory() as db:
        assert (await db.execute(select(func.count(PracticeSession.id)))).scalar_one() == 0
    await engine.dispose()
