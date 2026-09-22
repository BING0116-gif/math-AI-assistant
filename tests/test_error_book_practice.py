"""§5.1 错题专项练习（POST /api/practice/sessions/from-error-book 的服务层）回归测试。

服务端自查当前用户未掌握 ErrorItem 关联题目，客户端不拼题目列表；
顺序模式按最近错误时间倒序，随机模式由 seed 决定且可复现。
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint, Question,
    QuestionKnowledgePoint, User,
)
from app.services.practice_service import PracticeError, create_error_book_session, start_session, submit_attempt


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
        course = Course(id="course-1", code="calculus", name="高等数学", subject="math", default_version_id="version-1")
        version = KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published")
        chapter = Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="函数")
        point = KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限")
        db.add_all([
            course, version, chapter, point,
            User(id="user-1", username="student", email="student@example.test", password_hash="x"),
            User(id="user-2", username="other", email="other@example.test", password_hash="x"),
            User(id="user-3", username="clean", email="clean@example.test", password_hash="x"),
        ])
        await db.flush()
        base_time = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        for index in range(3):
            question = Question(
                id=f"Q-{index}", content=f"题{index}", question_type="choice",
                options=[{"id": "A", "text": "ok"}], answer="A", analysis="解析",
                category="高数", difficulty=2, course_id="course-1", version_id="version-1",
                review_status="published", grading_mode="deterministic", practice_eligible=True,
                answer_spec={"kind": "choice", "correct": "A"},
            )
            db.add(question); await db.flush()
            db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        # user-1 的错题：Q-0 最旧、Q-2 最新；Q-1 已掌握应排除
        db.add_all([
            ErrorItem(user_id="user-1", item_id="item-0", question="题0", question_id="Q-0", is_mastered=False,
                      source="attempt", wrong_attempt_count=2, updated_at=base_time),
            ErrorItem(user_id="user-1", item_id="item-2", question="题2", question_id="Q-2", is_mastered=False,
                      source="attempt", wrong_attempt_count=1, updated_at=base_time + timedelta(hours=2)),
            ErrorItem(user_id="user-1", item_id="item-1", question="题1", question_id="Q-1", is_mastered=True,
                      source="attempt", wrong_attempt_count=1, updated_at=base_time + timedelta(hours=1)),
        ])
        # 他人错题不得进入 user-1 的重练会话
        db.add(ErrorItem(user_id="user-2", item_id="item-o", question="他人题", question_id="Q-0", is_mastered=False,
                         source="attempt", wrong_attempt_count=1, updated_at=base_time + timedelta(hours=3)))
        await db.commit()
    return engine, factory


@pytest.mark.asyncio
async def test_error_book_session_scopes_to_owners_unmastered_items(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_error_book_session("user-1", idempotency_key="err-key-1")
    ids = [question["question_id"] for question in session["questions"]]
    assert ids == ["Q-2", "Q-0"]
    assert session["config"]["selection"] == "error_book"
    assert session["config"]["behavior"] == "immediate" and session["config"]["order_mode"] == "sequential"
    assert "answer_spec" not in session["questions"][0]
    assert (await create_error_book_session("user-1", idempotency_key="err-key-1"))["session_id"] == session["session_id"]
    other = await create_error_book_session("user-2", idempotency_key="err-key-2")
    assert [question["question_id"] for question in other["questions"]] == ["Q-0"]
    with pytest.raises(PracticeError, match="暂无待重练"):
        await create_error_book_session("user-3", idempotency_key="err-key-9")
    await engine.dispose()


@pytest.mark.asyncio
async def test_error_book_random_order_is_seed_deterministic(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    first = await create_error_book_session("user-1", order_mode="random", random_seed=42, idempotency_key="err-key-3")
    second = await create_error_book_session("user-1", order_mode="random", random_seed=42, idempotency_key="err-key-4")
    ids_first = [question["question_id"] for question in first["questions"]]
    ids_second = [question["question_id"] for question in second["questions"]]
    assert sorted(ids_first) == ["Q-0", "Q-2"]
    assert ids_first == ids_second
    assert first["config"]["order_mode"] == "random"
    await engine.dispose()


@pytest.mark.asyncio
async def test_error_book_session_supports_behavior_and_full_loop(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    session = await create_error_book_session(
        "user-1", behavior="immediate", order_mode="sequential", idempotency_key="err-key-5",
    )
    sid = session["session_id"]
    await start_session("user-1", sid)
    qid = session["questions"][0]["question_id"]
    wrong = await submit_attempt("user-1", sid, qid, "B", "err-attempt-1")
    assert wrong["correct"] is False
    retry = await submit_attempt("user-1", sid, qid, "A", "err-attempt-2")
    assert retry["correct"] is True and retry["retry_count"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_error_book_invalid_params_and_limit(monkeypatch):
    engine, _ = await _seed(monkeypatch)
    with pytest.raises(PracticeError, match="答题行为"):
        await create_error_book_session("user-1", behavior="bogus", idempotency_key="err-key-6")
    with pytest.raises(PracticeError, match="排序方式"):
        await create_error_book_session("user-1", order_mode="bogus", idempotency_key="err-key-7")
    limited = await create_error_book_session("user-1", max_questions=1, idempotency_key="err-key-8")
    assert len(limited["questions"]) == 1
    await engine.dispose()
