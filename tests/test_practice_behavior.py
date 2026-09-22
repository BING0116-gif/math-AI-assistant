"""§5.1 答题行为配置（immediate/adaptive/deferred）与练习中间态恢复的回归测试。

判分事实与掌握度权重严格分离：adaptive 衰减只进 learning_signals.mastery_weight，
永不改写 graded correct；deferred 在完成前不向学生泄露任何判分信息。
"""
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, Question, QuestionKnowledgePoint, User
from app.services.practice_service import (
    PracticeError, complete_session, create_session, get_session, save_practice_snapshot,
    start_session, submit_attempt,
)


def _base_config(**overrides):
    config = {
        "course_id": "course-1", "version_id": "version-1",
        "chapter_ids": ["chapter-1"], "knowledge_point_codes": [],
        "question_types": ["choice"], "question_count": 5,
        "idempotency_key": "create-key-1",
    }
    config.update(overrides)
    return config


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
        course = Course(id="course-1", code="calculus", name="高等数学", subject="math")
        version = KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published")
        chapter = Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="函数")
        point = KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限")
        db.add_all([course, version, chapter, point, User(id="user-1", username="student", email="student@example.test", password_hash="x")])
        await db.flush()
        for index in range(5):
            question = Question(
                id=f"Q-{index}", content=f"{index}+1=?", question_type="choice",
                options=[{"id": "A", "text": "ok"}], answer="A", analysis="解析",
                category="高数", difficulty=2, course_id="course-1", version_id="version-1",
                review_status="published", grading_mode="deterministic", practice_eligible=True,
                answer_spec={"kind": "choice", "correct": "A"},
            )
            db.add(question); await db.flush()
            db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()
    return engine, factory


@pytest.mark.asyncio
async def test_immediate_behavior_allows_single_retry_with_dual_record(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(behavior="immediate"))
    assert session["config"]["behavior"] == "immediate"
    sid = session["session_id"]
    qid = session["questions"][0]["question_id"]
    await start_session("user-1", sid)
    first = await submit_attempt("user-1", sid, qid, "B", "attempt-1")
    assert first["correct"] is False
    assert first["retry_count"] == 0 and len(first["submissions"]) == 1
    retry = await submit_attempt("user-1", sid, qid, "A", "attempt-2")
    assert retry["correct"] is True and retry["correct_answer"] == "A"
    assert retry["retry_count"] == 1
    assert [item["correct"] for item in retry["submissions"]] == [False, True]
    assert retry["learning_signals"]["retry"] is True
    assert (await submit_attempt("user-1", sid, qid, "A", "attempt-2"))["correct"] is True
    with pytest.raises(PracticeError, match="已提交"):
        await submit_attempt("user-1", sid, qid, "A", "attempt-3")
    await engine.dispose()


@pytest.mark.asyncio
async def test_immediate_retry_exhausted_after_second_wrong_answer(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(behavior="immediate", idempotency_key="create-key-2"))
    sid = session["session_id"]
    qid = session["questions"][0]["question_id"]
    await start_session("user-1", sid)
    await submit_attempt("user-1", sid, qid, "B", "attempt-1")
    second = await submit_attempt("user-1", sid, qid, "C", "attempt-2")
    assert second["correct"] is False and len(second["submissions"]) == 2
    with pytest.raises(PracticeError, match="已提交"):
        await submit_attempt("user-1", sid, qid, "A", "attempt-3")
    await engine.dispose()


@pytest.mark.asyncio
async def test_adaptive_behavior_decays_mastery_weight_not_the_grade(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(behavior="adaptive", idempotency_key="create-key-3"))
    sid = session["session_id"]
    qid = session["questions"][0]["question_id"]
    await start_session("user-1", sid)
    first = await submit_attempt("user-1", sid, qid, "B", "attempt-1")
    assert first["learning_signals"]["mastery_weight"] == 1.0
    second = await submit_attempt("user-1", sid, qid, "C", "attempt-2")
    assert second["learning_signals"]["mastery_weight"] == 0.6
    assert second["learning_signals"]["retry"] is True
    third = await submit_attempt("user-1", sid, qid, "A", "attempt-3")
    assert third["correct"] is True
    assert third["learning_signals"]["mastery_weight"] == 0.3
    assert [item["correct"] for item in third["submissions"]] == [False, False, True]
    with pytest.raises(PracticeError, match="已提交"):
        await submit_attempt("user-1", sid, qid, "A", "attempt-4")
    await engine.dispose()


@pytest.mark.asyncio
async def test_deferred_behavior_hides_feedback_until_completion(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(behavior="deferred", idempotency_key="create-key-4"))
    sid = session["session_id"]
    right, wrong = session["questions"][0]["question_id"], session["questions"][1]["question_id"]
    await start_session("user-1", sid)
    for qid, answer, key in ((right, "A", "attempt-1"), (wrong, "B", "attempt-2")):
        payload = await submit_attempt("user-1", sid, qid, answer, key)
        assert payload["submitted"] is True and payload["feedback_deferred"] is True
        assert "correct" not in payload and "correct_answer" not in payload and "analysis" not in payload
    replay = await submit_attempt("user-1", sid, wrong, "B", "attempt-2")
    assert "correct" not in replay
    with pytest.raises(PracticeError, match="已提交"):
        await submit_attempt("user-1", sid, wrong, "A", "attempt-3")
    loaded = await get_session("user-1", sid)
    assert loaded["feedback"][right] == {"question_id": right, "submitted": True, "feedback_deferred": True}
    assert loaded["feedback"][wrong] == {"question_id": wrong, "submitted": True, "feedback_deferred": True}
    report = await complete_session("user-1", sid)
    graded = {item["question_id"]: item for item in report["results"]}
    assert graded[right]["correct"] is True and graded[wrong]["correct"] is False
    assert graded[right]["correct_answer"] == "A"
    final = await get_session("user-1", sid)
    assert final["feedback"][right]["correct"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_config_replays_and_defaults_to_immediate(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    legacy = _base_config()
    session = await create_session("user-1", legacy)
    assert session["config"]["behavior"] == "immediate" and session["config"]["order_mode"] == "random"
    assert (await create_session("user-1", legacy))["session_id"] == session["session_id"]
    explicit_default = _base_config(behavior="immediate", order_mode="random")
    assert (await create_session("user-1", explicit_default))["session_id"] == session["session_id"]
    qid = session["questions"][0]["question_id"]
    await start_session("user-1", session["session_id"])
    await submit_attempt("user-1", session["session_id"], qid, "B", "attempt-1")
    await submit_attempt("user-1", session["session_id"], qid, "A", "attempt-2")
    with pytest.raises(PracticeError, match="已提交"):
        await submit_attempt("user-1", session["session_id"], qid, "A", "attempt-3")
    await engine.dispose()


@pytest.mark.asyncio
async def test_sequential_order_mode_sorts_by_question_id(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(order_mode="sequential", idempotency_key="create-key-5"))
    ids = [question["question_id"] for question in session["questions"]]
    assert ids == ["Q-0", "Q-1", "Q-2", "Q-3", "Q-4"]
    assert session["config"]["order_mode"] == "sequential"
    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_behavior_and_order_are_rejected(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    with pytest.raises(PracticeError, match="答题行为"):
        await create_session("user-1", _base_config(behavior="bogus", idempotency_key="create-key-6"))
    with pytest.raises(PracticeError, match="排序方式"):
        await create_session("user-1", _base_config(order_mode="bogus", idempotency_key="create-key-7"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_recovery_snapshot_roundtrip_and_validation(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_session("user-1", _base_config(idempotency_key="create-key-8"))
    sid = session["session_id"]
    qid = session["questions"][2]["question_id"]
    with pytest.raises(PracticeError, match="尚未开始"):
        await save_practice_snapshot("user-1", sid, qid)
    await start_session("user-1", sid)
    saved = await save_practice_snapshot("user-1", sid, qid)
    assert saved["completed"] is False and saved["current_question_id"] == qid
    loaded = await get_session("user-1", sid)
    assert loaded["recovery_snapshot"] == {"current_question_id": qid}
    assert loaded["recovery_snapshot_at"] is not None
    cleared = await save_practice_snapshot("user-1", sid, None)
    assert cleared["current_question_id"] is None
    with pytest.raises(PracticeError, match="不属于"):
        await save_practice_snapshot("user-1", sid, "Q-999")
    with pytest.raises(PracticeError, match="不存在"):
        await save_practice_snapshot("user-2", sid, qid)
    await engine.dispose()
