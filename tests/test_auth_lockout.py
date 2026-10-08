"""登录锁定链路（B2）回归测试。

原先 ``locked_until`` 是死列：既没有读取点，也没有写入口，``increment_failed_login``
从未被调用。这里锁住三件事：
1. 失败计数真实累加，达到阈值写入 ``locked_until`` 并立刻对外表现为 423；
2. 锁定期间即使口令正确也不能登录；解锁/成功后状态被清零；
3. 401 / 423 的响应契约（code + message + retry_after_seconds + Retry-After 头），
   以及"未知用户名"与"密码错误"对外不可区分。
"""

import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.api import auth as auth_api
from app.config.settings import settings
from app.data.models import Base, User
from app.middleware import auth as auth_module
from app.middleware.auth import (
    LoginOutcome,
    _hash_password,
    authenticate_user,
    authenticate_user_detailed,
)

PASSWORD = "correct pass"


def _now():
    return datetime.now(timezone.utc)


def _counter(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def _make_db(monkeypatch, *, username="testuser", password=PASSWORD, **user_kwargs):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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

    monkeypatch.setattr(auth_module, "get_db_session", _session)

    async with factory() as session:
        session.add(User(
            id="user-1",
            username=username,
            email=f"{username}@example.test",
            password_hash=_hash_password(password),
            **user_kwargs,
        ))
        await session.commit()

    monkeypatch.setattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5, raising=False)
    monkeypatch.setattr(settings, "LOGIN_LOCK_MINUTES", 15, raising=False)
    return engine, factory


async def _read_user(factory):
    async with factory() as session:
        return await session.scalar(select(User).where(User.id == "user-1"))


# ── 失败计数与锁定生效 ──

@pytest.mark.asyncio
async def test_wrong_password_increments_failed_count(monkeypatch):
    _, factory = await _make_db(monkeypatch)

    result = await authenticate_user_detailed("testuser", "nope")

    assert result.outcome is LoginOutcome.INVALID_CREDENTIALS
    assert result.reason == "wrong_password"
    user = await _read_user(factory)
    assert user.failed_login_count == 1
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_threshold_failures_lock_account(monkeypatch):
    _, factory = await _make_db(monkeypatch)

    for attempt in range(1, 5):
        result = await authenticate_user_detailed("testuser", "nope")
        assert result.outcome is LoginOutcome.INVALID_CREDENTIALS, attempt
        user = await _read_user(factory)
        assert user.failed_login_count == attempt

    result = await authenticate_user_detailed("testuser", "nope")
    assert result.outcome is LoginOutcome.LOCKED
    assert result.newly_locked is True
    assert result.retry_after_seconds == 15 * 60

    user = await _read_user(factory)
    assert user.locked_until is not None
    # 锁定即处罚：计数归零，解锁后仍可再试满阈值次数
    assert user.failed_login_count == 0


@pytest.mark.asyncio
async def test_correct_password_is_rejected_while_locked(monkeypatch):
    """锁定期间不做口令校验，也不给 token —— 否则锁定形同虚设。"""
    _, factory = await _make_db(monkeypatch)
    for _ in range(5):
        await authenticate_user_detailed("testuser", "nope")

    result = await authenticate_user_detailed("testuser", PASSWORD)

    assert result.outcome is LoginOutcome.LOCKED
    assert result.user is None
    assert 0 < result.retry_after_seconds <= 15 * 60


@pytest.mark.asyncio
async def test_naive_stored_lock_deadline_is_still_honoured(monkeypatch):
    """SQLite 读回的 DateTime(timezone=True) 是 naive；不得因 tz 比较抛异常。"""
    _, factory = await _make_db(monkeypatch, locked_until=_now() + timedelta(minutes=10))
    user = await _read_user(factory)
    assert user.locked_until.tzinfo is None  # 确认场景确实落在 naive 分支

    result = await authenticate_user_detailed("testuser", PASSWORD)
    assert result.outcome is LoginOutcome.LOCKED


@pytest.mark.asyncio
async def test_expired_lock_allows_login_and_clears_state(monkeypatch):
    _, factory = await _make_db(
        monkeypatch,
        locked_until=_now() - timedelta(minutes=1),
        failed_login_count=4,
    )

    result = await authenticate_user_detailed("testuser", PASSWORD)

    assert result.outcome is LoginOutcome.SUCCESS
    assert result.user is not None
    user = await _read_user(factory)
    assert user.locked_until is None
    assert user.failed_login_count == 0
    assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_unknown_and_inactive_users_are_indistinguishable(monkeypatch):
    await _make_db(monkeypatch, username="testuser", is_active=False)

    inactive = await authenticate_user_detailed("testuser", PASSWORD)
    unknown = await authenticate_user_detailed("ghost", PASSWORD)

    assert inactive.outcome is LoginOutcome.INVALID_CREDENTIALS
    assert unknown.outcome is LoginOutcome.INVALID_CREDENTIALS
    # 对外 code 相同（API 层只看 outcome），仅指标/审计可区分原因
    assert inactive.reason == "inactive_user"
    assert unknown.reason == "unknown_user"


@pytest.mark.asyncio
async def test_legacy_authenticate_user_wrapper_keeps_optional_contract(monkeypatch):
    """脚本与既有调用方依赖 ``Optional[DBUser]`` 语义，不能破坏。"""
    _, _factory = await _make_db(monkeypatch)

    assert await authenticate_user("testuser", PASSWORD) is not None
    assert await authenticate_user("testuser", "nope") is None
    assert await authenticate_user("ghost", "nope") is None

    for _ in range(5):
        await authenticate_user("testuser", "nope")
    assert await authenticate_user("testuser", PASSWORD) is None  # 已锁定


# ── API 契约：401 / 423 / 200 ──

def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_api.router)
    return TestClient(app)


def _login_body(username="testuser", password="nope"):
    return {"username": username, "password": password}


def _prepare(monkeypatch):
    """路由级测试只关心响应契约；限流本身在 test_security_rate_limit.py 覆盖。"""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-secret", raising=False)


def test_login_invalid_credentials_contract(monkeypatch):
    _prepare(monkeypatch)

    async def fake_authenticate(username, password, client_ip=""):
        from app.middleware.auth import AuthResult
        return AuthResult(outcome=LoginOutcome.INVALID_CREDENTIALS, reason="wrong_password")

    monkeypatch.setattr(auth_api, "authenticate_user_detailed", fake_authenticate)

    response = _client().post("/api/auth/login", json=_login_body())

    assert response.status_code == 401
    assert response.json() == {
        "code": "INVALID_CREDENTIALS",
        "message": "用户名或密码错误",
        "retry_after_seconds": None,
    }
    assert "retry-after" not in response.headers


def test_login_locked_contract(monkeypatch):
    _prepare(monkeypatch)

    async def fake_authenticate(username, password, client_ip=""):
        from app.middleware.auth import AuthResult
        return AuthResult(outcome=LoginOutcome.LOCKED, retry_after_seconds=640, reason="locked")

    monkeypatch.setattr(auth_api, "authenticate_user_detailed", fake_authenticate)

    response = _client().post("/api/auth/login", json=_login_body())

    assert response.status_code == 423
    assert response.headers["Retry-After"] == "640"
    body = response.json()
    assert body["code"] == "ACCOUNT_LOCKED"
    assert body["retry_after_seconds"] == 640
    assert "密码" not in body["message"]  # 不透露口令相关信息


def test_login_success_payload_shape_unchanged(monkeypatch):
    """成功响应结构必须逐字段保持原样（前端 authStore 直接解构）。"""
    _prepare(monkeypatch)

    from types import SimpleNamespace
    from app.middleware.auth import AuthResult, TokenPair

    fake_user = SimpleNamespace(id="user-1", username="testuser", role="student")

    async def fake_authenticate(username, password, client_ip=""):
        return AuthResult(outcome=LoginOutcome.SUCCESS, user=fake_user)

    async def fake_token_pair(*_args, **_kwargs):
        return TokenPair(
            access_token="a", refresh_token="r", token_type="bearer", expires_in=60
        )

    monkeypatch.setattr(auth_api, "authenticate_user_detailed", fake_authenticate)
    monkeypatch.setattr(auth_api, "create_token_pair", fake_token_pair)

    response = _client().post(
        "/api/auth/login", json=_login_body(password=PASSWORD)
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "data": {
            "user_id": "user-1",
            "username": "testuser",
            "role": "student",
            "access_token": "a",
            "refresh_token": "r",
            "token_type": "bearer",
            "expires_in": 60,
        },
    }


def test_login_metrics_and_lockout_counter_advance(monkeypatch):
    _prepare(monkeypatch)

    from app.middleware.auth import AuthResult

    before_failures = _counter("mathai_login_failures_total", reason="wrong_password")
    before_lockouts = _counter("mathai_account_lockouts_total")

    async def fake_wrong(username, password, client_ip=""):
        return AuthResult(outcome=LoginOutcome.INVALID_CREDENTIALS, reason="wrong_password")

    async def fake_lock(username, password, client_ip=""):
        return AuthResult(
            outcome=LoginOutcome.LOCKED, retry_after_seconds=900, newly_locked=True
        )

    client = _client()
    monkeypatch.setattr(auth_api, "authenticate_user_detailed", fake_wrong)
    client.post("/api/auth/login", json=_login_body())
    monkeypatch.setattr(auth_api, "authenticate_user_detailed", fake_lock)
    client.post("/api/auth/login", json=_login_body())

    assert _counter("mathai_login_failures_total", reason="wrong_password") == before_failures + 1
    assert _counter("mathai_account_lockouts_total") == before_lockouts + 1
