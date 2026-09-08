"""T02 · 间隔复习闭环（ReviewScheduler）回归测试。

用内存 SQLite 直连服务层：验证"练习答错自动首排 → 复习答对延长 / 再答错重置置顶 →
毕业退出队列 → 到期查询"这条可重复运行的状态机，以及 event_id 重放幂等。
"""
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import (
    Base, Course, ErrorItem, KnowledgeGraphVersion, PracticeAttempt,
    PracticeSession, PracticeSessionQuestion, Question, User,
)
from app.services.error_review import capture_wrong_attempt, record_review_evidence
from app.services.review_scheduler import (
    SCHEDULER_VERSION,
    compute_next_interval,
    get_due_reviews,
)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ---- 纯函数：间隔策略 ----
def test_interval_doubles_on_correct_and_caps():
    days = 1
    seq = []
    for _ in range(7):
        days = compute_next_interval(current_interval_days=days, correct=True)
        seq.append(days)
    assert seq == [2, 4, 8, 16, 30, 30, 30]  # ×2 放大，封顶 30 天


def test_interval_resets_on_wrong_and_legacy_zero_uses_first_interval():
    assert compute_next_interval(current_interval_days=8, correct=False) == settings.REVIEW_FIRST_INTERVAL_DAYS
    # 历史数据 interval=0（从未被排期）按首次间隔处理
    assert compute_next_interval(current_interval_days=0, correct=True) == settings.REVIEW_FIRST_INTERVAL_DAYS * 2


@pytest.mark.asyncio
async def test_wrong_attempt_creates_first_schedule_and_wrong_again_resets():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        db.add_all([
            User(id="user-1", username="u1", email="u1@example.test", password_hash="x"),
            Course(id="course-1", code="calculus", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1", name="V1"),
        ])
        await db.flush()
        db.add(Question(
            id="Q-1", content="1+1=?", question_type="choice", answer="A",
            answer_spec={"kind": "choice", "correct": "A"}, category="高数",
            course_id="course-1", version_id="version-1",
        ))
        await db.flush()
        session = PracticeSession(id="s1", user_id="user-1", mode="practice", status="in_progress", course_id="course-1", version_id="version-1", config_snapshot={}, random_seed=1, idempotency_key="s1")
        db.add(session)
        await db.flush()
        row = PracticeSessionQuestion(id=1, session_id="s1", question_id="Q-1", position=1, snapshot={})
        db.add(row)
        await db.flush()
        attempt = PracticeAttempt(id="a1", user_id="user-1", session_id="s1", session_question_id=1, question_id="Q-1", user_answer="B", correct=False, grading_snapshot={"correct_answer": "A"}, idempotency_key="a1")
        db.add(attempt)
        item = await capture_wrong_attempt(db, attempt=attempt, question_snapshot={"content": "1+1=?", "question_type": "choice", "knowledge_point_codes": ["limit"]}, classification={"reason": "概念错误", "confidence": 1.0})
        await db.flush()

        # 验收：做错题后自动进入明确的首次复习排期（不靠前端兜底）
        assert item.next_review_at is not None
        assert item.scheduler_version == SCHEDULER_VERSION
        assert item.review_interval_days == settings.REVIEW_FIRST_INTERVAL_DAYS
        assert item.review_streak == 0
        delta = item.next_review_at - _now()
        assert 0 <= delta.total_seconds() <= 86400 * settings.REVIEW_FIRST_INTERVAL_DAYS

        # 复习答对一次：间隔 1 -> 2，streak 1
        await record_review_evidence(db, user_id="user-1", item_id=item.item_id, event_type="original_correct", event_id="rev-1")
        assert item.review_interval_days == settings.REVIEW_FIRST_INTERVAL_DAYS * settings.REVIEW_CORRECT_MULTIPLIER
        assert item.review_streak == 1
        assert item.next_review_at is not None

        # 再次答错：间隔回到 1 天、streak 清零、review_state 置回 new（查询中天然置顶）
        # 注意：practice_attempts 对 session_question_id 有唯一约束，再错作答需放进新会话。
        session2 = PracticeSession(id="s2", user_id="user-1", mode="practice", status="in_progress", course_id="course-1", version_id="version-1", config_snapshot={}, random_seed=2, idempotency_key="s2")
        db.add(session2)
        await db.flush()
        row2 = PracticeSessionQuestion(id=2, session_id="s2", question_id="Q-1", position=1, snapshot={})
        db.add(row2)
        await db.flush()
        attempt2 = PracticeAttempt(id="a2", user_id="user-1", session_id="s2", session_question_id=2, question_id="Q-1", user_answer="C", correct=False, grading_snapshot={"correct_answer": "A"}, idempotency_key="a2")
        db.add(attempt2)
        item = await capture_wrong_attempt(db, attempt=attempt2, question_snapshot={"content": "1+1=?", "question_type": "choice", "knowledge_point_codes": ["limit"]}, classification={"reason": "概念错误", "confidence": 1.0})
        assert item.review_state == "new" and not item.is_mastered
        assert item.review_interval_days == settings.REVIEW_FIRST_INTERVAL_DAYS
        assert item.review_streak == 0
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_replay_same_review_event_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        db.add(User(id="user-1", username="u1", email="u1@example.test", password_hash="x"))
        await db.flush()
        item = ErrorItem(user_id="user-1", item_id="e1", question="x?", review_state="new", knowledge_point_codes=["limit"], source="attempt")
        db.add(item)
        await db.flush()
        from app.services.review_scheduler import schedule_new_error
        schedule_new_error(item, now=_now())
        await db.flush()
        first_next, first_interval = item.next_review_at, item.review_interval_days

        await record_review_evidence(db, user_id="user-1", item_id="e1", event_type="original_correct", event_id="rev-dup")
        extended_next = item.next_review_at
        assert item.review_interval_days == settings.REVIEW_FIRST_INTERVAL_DAYS * settings.REVIEW_CORRECT_MULTIPLIER

        # 同一 event_id 重放：不重复推进状态、不重复延后排期
        await record_review_evidence(db, user_id="user-1", item_id="e1", event_type="original_correct", event_id="rev-dup")
        assert item.next_review_at == extended_next
        assert item.review_interval_days == first_interval * settings.REVIEW_CORRECT_MULTIPLIER
        assert item.review_state == "understanding"
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_mastered_error_exits_review_queue():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        db.add(User(id="user-1", username="u1", email="u1@example.test", password_hash="x"))
        await db.flush()
        item = ErrorItem(user_id="user-1", item_id="e1", question="x?", review_state="new", knowledge_point_codes=["limit"], source="attempt")
        db.add(item)
        await db.flush()
        from app.services.review_scheduler import schedule_new_error
        schedule_new_error(item, now=_now())

        await record_review_evidence(db, user_id="user-1", item_id="e1", event_type="original_correct", event_id="r1")
        assert item.next_review_at is not None
        await record_review_evidence(db, user_id="user-1", item_id="e1", event_type="variant_correct", event_id="r2")
        await record_review_evidence(db, user_id="user-1", item_id="e1", event_type="spaced_correct", event_id="r3")
        assert item.review_state == "mastered" and item.is_mastered
        # 毕业：取消排期，不再进入复习队列
        assert item.next_review_at is None
        due = await get_due_reviews(db, user_id="user-1")
        assert due == []
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_due_reviews_filters_orders_and_isolates_users():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        db.add_all([
            User(id="user-1", username="u1", email="u1@example.test", password_hash="x"),
            User(id="user-2", username="u2", email="u2@example.test", password_hash="x"),
        ])
        await db.flush()
        now = _now()
        # user-1：到期"巩固中"（更早到期）+ 到期"新错"（活跃置顶）+ 未到期 + 未排期历史题
        db.add_all([
            ErrorItem(user_id="user-1", item_id="consolidating-due", question="q1", review_state="consolidating", knowledge_point_codes=["kp-a"], source="attempt", is_mastered=False, next_review_at=now.replace(microsecond=0), review_interval_days=4, review_streak=2, scheduler_version=SCHEDULER_VERSION),
            ErrorItem(user_id="user-1", item_id="new-due", question="q2", review_state="new", knowledge_point_codes=["kp-b"], source="attempt", is_mastered=False, next_review_at=now.replace(microsecond=0), review_interval_days=1, review_streak=0, scheduler_version=SCHEDULER_VERSION),
            ErrorItem(user_id="user-1", item_id="not-due", question="q3", review_state="understanding", knowledge_point_codes=["kp-c"], source="attempt", is_mastered=False, next_review_at=now.replace(microsecond=0) + __import__("datetime").timedelta(days=3), review_interval_days=2, review_streak=1, scheduler_version=SCHEDULER_VERSION),
            ErrorItem(user_id="user-1", item_id="legacy-unscheduled", question="q4", review_state="new", knowledge_point_codes=["kp-d"], source="attempt", is_mastered=False, next_review_at=None),
            # user-2 的到期错题：不应泄漏给 user-1（user_id 隔离）
            ErrorItem(user_id="user-2", item_id="other-due", question="q5", review_state="new", knowledge_point_codes=["kp-e"], source="attempt", is_mastered=False, next_review_at=now.replace(microsecond=0), review_interval_days=1, review_streak=0, scheduler_version=SCHEDULER_VERSION),
        ])
        await db.commit()

        due = await get_due_reviews(db, user_id="user-1", now=now)
        assert [i.item_id for i in due] == ["new-due", "consolidating-due"]  # 活跃错题优先于巩固题
        due_user2 = await get_due_reviews(db, user_id="user-2", now=now)
        assert [i.item_id for i in due_user2] == ["other-due"]
    await engine.dispose()
