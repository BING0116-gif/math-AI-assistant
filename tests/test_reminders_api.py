"""提醒中心（A1）回归测试。

提醒中心刻意不建 notifications 表：它是 ``due_reviews`` + ``today_hub`` 的派生视图。
因此本文件锁住的是"派生正确 + 不越权 + 不新增可写状态"这三件事：
1. overdue/today/upcoming 分档与角标计数（含"刚被稍后提醒过的排期"不得重复出现）；
2. 只按认证上下文里的 user_id 取数，客户端无法指定他人；
3. 错题级排期项不可 defer（ErrorItem 没有 deferred_until），知识点级可以且幂等。
"""

import contextlib
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import learning_hub_api
from app.config.middleware_config import middleware_config
from app.data.models import (
    Base, Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint,
    ReviewSchedule, User,
)
from app.services.learning_hub import LearningHubError, defer_review
from app.services.reminders import (
    BUCKET_OVERDUE, BUCKET_TODAY, BUCKET_UPCOMING,
    ERROR_ITEM_DEFER_DISABLED, REMINDERS_VERSION,
    _classify, _parse_due, build_reminders,
)

# 种子与断言共用同一个"现在"：分档窗口是 24h/48h 量级，用例运行时间远小于该尺度。
NOW = datetime.now(timezone.utc)


def _at(**kwargs):
    return NOW + timedelta(**kwargs)


async def _make_db(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    @contextlib.asynccontextmanager
    async def _session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr("app.services.learning_hub.get_db_session", _session)

    async with factory() as session:
        session.add_all([
            User(id="rem-a", username="rem-a", email="a@rem.test", password_hash="x"),
            User(id="rem-b", username="rem-b", email="b@rem.test", password_hash="x"),
            Course(id="rem-course", code="rem-course", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="rem-version", course_id="rem-course", version="1", name="V1"),
            Chapter(id="rem-chapter", course_id="rem-course", version_id="rem-version",
                    code="rem-ch", name="极限与连续", sort_order=1, level=1),
        ])
        await session.flush()
        session.add_all([
            KnowledgePoint(course_id="rem-course", version_id="rem-version", chapter_id="rem-chapter",
                           code="LIMIT", name="数列极限", difficulty=3),
            # 知识点级排期：逾期 3 天 / 2 小时前到期 / 6 小时后到期 / 30 天后（必须被排除）
            ReviewSchedule(user_id="rem-a", knowledge_point_code="LIMIT", due_at=_at(days=-3),
                           interval_days=7, review_count=2, stage=2),
            ReviewSchedule(user_id="rem-a", knowledge_point_code="CONT", due_at=_at(hours=-2), interval_days=1),
            ReviewSchedule(user_id="rem-a", knowledge_point_code="SERIES", due_at=_at(hours=6), interval_days=3),
            ReviewSchedule(user_id="rem-a", knowledge_point_code="TRIPLE", due_at=_at(days=30), interval_days=15),
            # 被"稍后提醒"推到未来的排期：due_at 已过期，effective_due 在未来
            ReviewSchedule(user_id="rem-a", knowledge_point_code="DERIV", due_at=_at(hours=-1),
                           interval_days=1, deferred_until=_at(hours=10)),
            ReviewSchedule(user_id="rem-b", knowledge_point_code="LIMIT", due_at=_at(hours=-1), interval_days=1),
        ])
        await session.flush()
        session.add_all([
            # 错题级排期：有 next_review_at，无 deferred_until 概念
            ErrorItem(user_id="rem-a", item_id="err-001", question="求极限",
                      knowledge_point_codes=["LIMIT"], is_mastered=False, review_state="consolidating",
                      next_review_at=_at(minutes=-30), review_interval_days=3, review_streak=1,
                      scheduler_version="error-review-scheduler-v1"),
            ErrorItem(user_id="rem-a", item_id="err-unranked", question="未排期错题",
                      knowledge_point_codes=["LIMIT"], is_mastered=False, next_review_at=None),
        ])
        await session.commit()
    return engine


class _State:
    def __init__(self, user_id):
        self.user_id = user_id


class _FakeRequest:
    """只带 state 的最小 Request 替身：端点只用 request.state.user_id。"""

    def __init__(self, user_id):
        self.state = _State(user_id)


async def _reminders(user_id="rem-a", limit=50):
    return await build_reminders(user_id, limit=limit)


def _by_key(items):
    return {item["key"]: item for item in items}


def _code_map(items):
    return {item["knowledge_point_code"]: item["bucket"] for item in items}


# ── 派生分档 ──

@pytest.mark.asyncio
async def test_buckets_and_counts_are_derived_without_a_new_table(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        payload = await _reminders()
        buckets = _code_map(payload["items"])
        assert buckets["CONT"] == BUCKET_TODAY
        assert buckets["SERIES"] == BUCKET_UPCOMING
        # 30 天后才到期：不属于提醒窗口，不得挤进面板
        assert "TRIPLE" not in buckets
        # 被 defer 的排期按 effective_due 归档到 upcoming，而不是仍算"已到期"
        assert buckets["DERIV"] == BUCKET_UPCOMING
        assert payload["version"] == REMINDERS_VERSION
        # 逾期项排在最前：角标紧迫度与列表顺序同向
        assert payload["items"][0]["knowledge_point_code"] == "LIMIT"
        assert payload["items"][0]["bucket"] == BUCKET_OVERDUE
        assert payload["items"][0]["overdue_minutes"] >= 3 * 24 * 60
        assert payload["items"][0]["hint"].startswith("逾期")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_counts_add_up_and_duplicate_rows_are_merged(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        payload = await _reminders()
        counts = payload["counts"]
        assert counts["total"] == len(payload["items"])
        assert counts["overdue"] + counts["today"] + counts["upcoming"] == counts["total"]
        # 未排期错题（next_review_at IS NULL）不产生提醒
        assert all(item["error_item_id"] != "err-unranked" for item in payload["items"])
        keys = [item["key"] for item in payload["items"]]
        assert len(keys) == len(set(keys)), "两次 due_reviews 取回的同一条排期必须去重"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reminders_only_expose_the_authenticated_users_own_rows(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        mine = await _reminders("rem-a")
        other = await _reminders("rem-b")
        assert [item["knowledge_point_code"] for item in other["items"]] == ["LIMIT"]
        assert other["counts"]["total"] == 1
        assert other["counts"]["today"] == 1
        assert mine["counts"]["total"] > other["counts"]["total"]
        empty = await _reminders("rem-none")
        assert empty["items"] == [] and empty["counts"]["total"] == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_primary_task_is_passed_through_from_today_hub(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        payload = await _reminders()
        # 主任务取自 today_hub，不在提醒中心重算优先级
        assert payload["primary"]["id"] == "review:LIMIT"
        assert payload["primary"]["evidence"]
        cold = await _reminders("rem-none")
        assert cold["primary"]["type"] == "diagnostic"
    finally:
        await engine.dispose()


# ── 深链与 defer 能力边界 ──

@pytest.mark.asyncio
async def test_deep_links_reuse_existing_routes(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        items = _by_key((await _reminders())["items"])
        schedule = items[next(k for k, v in items.items() if v["knowledge_point_code"] == "CONT")]
        # 知识点级：提醒中心只握有 code，KnowledgeCatalogView 的 ?point= 已同时接受 code
        assert schedule["action"]["route"] == "/knowledge"
        assert schedule["action"]["query"] == {"point": "CONT"}
        assert schedule["knowledge_point_name"] == "数列极限" or schedule["knowledge_point_code"] == "CONT"
        error = items[next(k for k, v in items.items() if v["source"] == "error_item")]
        # 错题级：复用既有 /error-book/:errorId（ErrorBookView 按 item_id 打开详情）
        assert error["action"]["route"] == "/error-book/err-001"
        assert error["kind"] == "error_review"
        assert error["error_item_id"] == "err-001"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_error_item_reminders_cannot_be_deferred(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        items = (await _reminders())["items"]
        error = next(item for item in items if item["source"] == "error_item")
        assert error["can_defer"] is False
        assert error["schedule_id"] is None
        assert error["defer_disabled_reason"] == ERROR_ITEM_DEFER_DISABLED
        assert error["title"].startswith("重练错题")
        schedule = next(item for item in items if item["source"] == "knowledge_point")
        assert schedule["can_defer"] is True
        assert isinstance(schedule["schedule_id"], int)
        assert schedule["defer_disabled_reason"] is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_defer_is_replayed_idempotently_and_moves_the_reminder(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        items = _by_key((await _reminders())["items"])
        target = items[next(k for k, v in items.items() if v["knowledge_point_code"] == "CONT")]
        key = "defer-reminders-0001"
        first = await defer_review("rem-a", target["schedule_id"], hours=24, idempotency_key=key)
        second = await defer_review("rem-a", target["schedule_id"], hours=24, idempotency_key=key)
        assert first == second
        with pytest.raises(LearningHubError) as conflict:
            await defer_review("rem-a", target["schedule_id"], hours=48, idempotency_key=key)
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"

        after = _by_key((await _reminders())["items"])
        moved = after[next(k for k, v in after.items() if v["knowledge_point_code"] == "CONT")]
        assert moved["bucket"] == BUCKET_UPCOMING
        assert list(after).count(target["key"]) == 1
    finally:
        await engine.dispose()


# ── API 层契约 ──

@pytest.mark.asyncio
async def test_endpoint_takes_user_id_only_from_request_state(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        response = await learning_hub_api.get_reminders(_FakeRequest("rem-b"), limit=50)
        validated = learning_hub_api.RemindersResponse.model_validate(response)
        assert validated.counts.total == 1
        assert validated.version == REMINDERS_VERSION
        # 客户端无法改判要看谁的数据：签名里根本没有 user_id
        assert "user_id" not in inspect.signature(learning_hub_api.get_reminders).parameters
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_endpoint_requires_authentication(monkeypatch):
    engine = await _make_db(monkeypatch)
    try:
        with pytest.raises(HTTPException) as exc:
            await learning_hub_api.get_reminders(_FakeRequest(None), limit=50)
        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == "UNAUTHENTICATED"
    finally:
        await engine.dispose()


def test_reminders_route_is_registered_and_not_rate_limit_exempt():
    route = next(
        (item for item in learning_hub_api.router.routes
         if getattr(item, "path", None) == "/api/learning/reminders"), None,
    )
    assert route is not None, "GET /api/learning/reminders 未注册"
    assert route.methods == {"GET"}
    assert route.response_model is learning_hub_api.RemindersResponse
    # 提醒端点必须走认证与限流（general 桶），否则又变成一个可被无限轮询的口子
    assert "/api/learning/reminders" not in middleware_config.RATE_LIMIT_SKIP_PATHS
    assert "/api/learning/reminders" not in middleware_config.NO_AUTH_PATHS


def test_response_shape_is_json_serializable():
    payload = {
        "generated_at": NOW,
        "version": REMINDERS_VERSION,
        "counts": {"overdue": 1, "today": 1, "upcoming": 1, "total": 3},
        "items": [{
            "key": "review_schedule:1", "kind": "review_schedule", "bucket": "overdue",
            "source": "knowledge_point", "schedule_id": 1, "knowledge_point_code": "LIMIT",
            "knowledge_point_name": "数列极限", "due_at": NOW - timedelta(days=3),
            "overdue_minutes": 4320, "title": "复习 数列极限", "hint": "逾期 3 天",
            "can_defer": True, "action": {"route": "/knowledge", "query": {"point": "LIMIT"}},
        }],
        "primary": None,
    }
    dumped = learning_hub_api.RemindersResponse.model_validate(payload).model_dump(mode="json")
    assert dumped["items"][0]["due_at"].endswith("Z") or "+" in dumped["items"][0]["due_at"]
    assert dumped["items"][0]["bucket"] == "overdue"
    assert dumped["items"][0]["defer_disabled_reason"] is None


# ── 纯函数：时间解析与分档 ──

@pytest.mark.parametrize("value", ["", "  ", None, "not-a-date", 123])
def test_unparsable_due_at_degrades_to_today_instead_of_vanishing(value):
    assert _parse_due(value) is None
    bucket, overdue_minutes, hint = _classify(None, NOW)
    assert bucket == BUCKET_TODAY
    assert overdue_minutes == 0
    assert hint == "今日到期"


def test_window_boundaries_are_exclusive_at_the_edges():
    assert _classify(_at(hours=-25), NOW)[0] == BUCKET_OVERDUE
    assert _classify(_at(hours=-24), NOW)[0] == BUCKET_TODAY
    assert _classify(NOW, NOW)[0] == BUCKET_TODAY
    assert _classify(_at(hours=48), NOW)[0] == BUCKET_UPCOMING
    # 超出 48h 窗口的未来排期被丢弃（返回空档位）
    assert _classify(_at(hours=49), NOW)[0] == ""


def test_naive_iso_strings_are_normalised_to_utc():
    naive = _parse_due(_at(hours=-2).replace(tzinfo=None).isoformat())
    assert naive.tzinfo is not None
    assert _classify(naive, NOW)[0] == BUCKET_TODAY
