"""限流身份解析与分桶预算的回归测试（B1）。

覆盖两类真实事故：
1. 生产反代下 ``request.client.host`` 恒为 nginx 容器 IP —— 所有学生共用一个桶。
2. NO_AUTH 与限流耦合 —— ``/api/auth/login`` 完全不限量，可被无限暴力尝试。
"""

import json

import pytest

from app.config.middleware_config import middleware_config
from app.config.settings import settings
from app.middleware import rate_limit as rate_limit_module  # noqa: F401  (确保模块可导入)
from app.middleware.client_identity import (
    _client_from_forwarded,
    resolve_client_ip,
    resolve_rate_limit_key,
    trusted_networks,
)
from app.middleware.path_matcher import (
    BUCKET_AUTH,
    BUCKET_AUTH_LOGIN,
    BUCKET_GENERAL,
    PathMatcher,
)
from app.middleware.rate_limit import RateLimitMiddleware


def _scope(
    path="/api/chat",
    method="POST",
    client=("172.18.0.10", 5555),
    headers=(),
    state=None,
):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": client,
        "server": ("testserver", 80),
        "state": dict(state or {}),
    }
    return scope


def _request(**kwargs):
    from starlette.requests import Request

    return Request(_scope(**kwargs))


def _matcher() -> PathMatcher:
    return PathMatcher(
        static_paths=list(middleware_config.STATIC_PATHS),
        skip_paths=list(middleware_config.NO_AUTH_PATHS),
        rate_limit_skip_paths=list(middleware_config.RATE_LIMIT_SKIP_PATHS),
        rate_limit_always_paths=list(middleware_config.RATE_LIMIT_ALWAYS_PATHS),
    )


@pytest.fixture(autouse=True)
def _pin_trusted_cidrs(monkeypatch):
    """IP 解析结果不应受本机 .env 影响。"""
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "172.16.0.0/12,127.0.0.1", raising=False)


def _build_middleware(max_requests=3, bucket_limits=None):
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return RateLimitMiddleware(
        inner,
        window_seconds=60,
        max_requests=max_requests,
        path_matcher=_matcher(),
        bucket_limits=bucket_limits,
    )


async def _call(middleware, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    status = sent[0]["status"]
    raw = sent[1].get("body") or b""
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = {"raw": raw.decode("utf-8", "replace")}
    headers = dict(sent[0].get("headers") or [])
    return status, body, headers


# ── 客户端 IP 解析 ──

def test_untrusted_socket_peer_ignores_forged_forwarded_for():
    """直连 8000 时（对端不在可信网段），客户端自带的 XFF 必须被忽略。"""
    request = _request(
        client=("198.51.100.9", 1234),
        headers=[("X-Forwarded-For", "1.1.1.1, 2.2.2.2")],
    )
    assert resolve_client_ip(request) == "198.51.100.9"


def test_trusted_proxy_uses_real_client_from_chain():
    request = _request(
        client=("172.18.0.2", 1234),
        headers=[("X-Forwarded-For", "203.0.113.7")],
    )
    assert resolve_client_ip(request) == "203.0.113.7"


def test_forged_leftmost_entry_is_not_treated_as_client():
    """客户端伪造 "1.1.1.1, <真实IP>"，nginx 追加对端 → 从右往左取第一个非可信地址。"""
    networks = trusted_networks("172.16.0.0/12,127.0.0.1")
    assert _client_from_forwarded("1.1.1.1, 203.0.113.7, 172.18.0.2", networks) == "203.0.113.7"


def test_fully_trusted_chain_falls_back_to_rightmost():
    networks = trusted_networks("172.16.0.0/12,127.0.0.1")
    assert _client_from_forwarded("172.18.0.3, 172.18.0.2", networks) == "172.18.0.2"


def test_unknown_marker_and_empty_chain_are_skipped():
    networks = trusted_networks("172.16.0.0/12,127.0.0.1")
    assert _client_from_forwarded("unknown, 203.0.113.7", networks) == "203.0.113.7"
    assert _client_from_forwarded("", networks) is None
    assert _client_from_forwarded("unknown", networks) is None


def test_misconfigured_cidr_does_not_break_resolution():
    """单项配错只跳过，不让整条限流退化成"全部不可信"。"""
    networks = trusted_networks("not-a-cidr,172.16.0.0/12")
    assert len(networks) == 1
    request = _request(
        client=("172.18.0.2", 1234),
        headers=[("X-Forwarded-For", "203.0.113.7")],
    )
    assert resolve_client_ip(request) == "203.0.113.7"


# ── 限流桶键 ──

def test_rate_limit_key_prefers_user_over_ip():
    request = _request(state={"user_id": "user-a"}, client=("172.18.0.2", 1))
    assert resolve_rate_limit_key(request) == "u:user-a"


def test_rate_limit_key_uses_real_ip_when_anonymous():
    request = _request(
        client=("172.18.0.2", 1),
        headers=[("X-Forwarded-For", "203.0.113.7")],
    )
    assert resolve_rate_limit_key(request) == "ip:203.0.113.7"


# ── NO_AUTH 与限流解耦 ──

@pytest.mark.parametrize(
    "path", ["/api/auth/login", "/api/auth/register", "/api/auth/refresh"]
)
def test_auth_password_paths_are_never_rate_limit_exempt(path):
    request = _request(path=path, method="POST")
    assert _matcher().should_skip_rate_limit(request) is False


def test_health_metrics_and_docs_stay_exempt_after_decoupling():
    """这些路径原先靠 NO_AUTH 间接豁免；解耦后必须由 RATE_LIMIT_SKIP_PATHS 显式覆盖。"""
    matcher = _matcher()
    for path in ("/api/health", "/api/health/ready", "/metrics", "/docs", "/openapi.json"):
        assert matcher.should_skip_rate_limit(_request(path=path, method="GET")) is True, path


def test_polling_and_static_stay_exempt():
    matcher = _matcher()
    assert matcher.should_skip_rate_limit(
        _request(path="/api/learning/activities/xxx/heartbeat", method="POST")
    ) is True
    assert matcher.should_skip_rate_limit(
        _request(path="/assets/index-abc123.js", method="GET")
    ) is True
    assert matcher.should_skip_rate_limit(_request(path="/dashboard", method="GET")) is True


def test_bucket_assignment():
    matcher = _matcher()
    assert matcher.rate_limit_bucket("/api/auth/login") == BUCKET_AUTH_LOGIN
    assert matcher.rate_limit_bucket("/api/auth/register") == BUCKET_AUTH_LOGIN
    assert matcher.rate_limit_bucket("/api/auth/refresh") == BUCKET_AUTH
    assert matcher.rate_limit_bucket("/api/auth/me") == BUCKET_AUTH
    assert matcher.rate_limit_bucket("/api/chat") == BUCKET_GENERAL


def test_prefix_match_does_not_over_match():
    matcher = _matcher()
    # /api/health 前缀不应命中 /api/healthprofile
    assert matcher.should_skip_rate_limit(_request(path="/api/healthprofile", method="GET")) is False


# ── 中间件行为：per-user 预算隔离 ──

@pytest.mark.asyncio
async def test_two_users_get_independent_budgets(monkeypatch):
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: None)
    middleware = _build_middleware(max_requests=2)

    for _ in range(2):
        status, _, _ = await _call(middleware, _scope(state={"user_id": "user-a"}))
        assert status == 200

    # user-a 预算耗尽
    status, body, headers = await _call(middleware, _scope(state={"user_id": "user-a"}))
    assert status == 429
    assert body["detail"] == "请求过于频繁，请稍后再试"
    assert int(headers[b"retry-after"]) >= 1

    # 但同一 nginx IP 下的 user-b 不受牵连（原事故根因）
    status, _, _ = await _call(middleware, _scope(state={"user_id": "user-b"}))
    assert status == 200


@pytest.mark.asyncio
async def test_anonymous_clients_on_same_proxy_get_separate_budgets(monkeypatch):
    """未认证请求也按真实出口 IP 分桶，而不是代理容器 IP。"""
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: None)
    middleware = _build_middleware(max_requests=2)

    for ip in ("203.0.113.1", "203.0.113.2"):
        for expected in (200, 200, 429):
            status, _, _ = await _call(
                middleware,
                _scope(path="/api/recognize", headers=[("X-Forwarded-For", ip)]),
            )
            assert status == expected, f"{ip} 第 {expected} 阶段异常"
        # 另一个出口 IP 的预算不被消耗
        assert f"general:ip:{ip}" in middleware._store


@pytest.mark.asyncio
async def test_login_bucket_is_ip_keyed_and_tighter(monkeypatch):
    """即便攻击者附带合法 token（会产出 u: 键），口令桶仍按 IP 计数。"""
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: None)
    middleware = _build_middleware(
        max_requests=100,
        bucket_limits={BUCKET_AUTH_LOGIN: 2, BUCKET_AUTH: 100, BUCKET_GENERAL: 100},
    )

    for user in ("user-a", "user-b", "user-c"):
        scope = _scope(
            path="/api/auth/login",
            headers=[("X-Forwarded-For", "203.0.113.9"), ("Authorization", "Bearer t")],
            state={"user_id": user},
        )
        status, _, _ = await _call(middleware, scope)
        # 同一 IP 的第 3 次登录必须被拒，与 user_id 无关
        expected = 200 if user in ("user-a", "user-b") else 429
        assert status == expected, f"{user} -> {status}"


# ── Redis 优先 + 异常降级 ──

class _FakeRedis:
    def __init__(self, fail=False):
        self.counters = {}
        self.expires = {}
        self.fail = fail

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("connection refused")
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, seconds):
        self.expires[key] = seconds

    async def ttl(self, key):
        return 17


@pytest.mark.asyncio
async def test_redis_fixed_window_is_used_with_namespaced_key(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: fake)
    middleware = _build_middleware(max_requests=2)

    for _ in range(2):
        status, _, _ = await _call(middleware, _scope(state={"user_id": "user-a"}))
        assert status == 200

    status, _, headers = await _call(middleware, _scope(state={"user_id": "user-a"}))
    assert status == 429
    assert headers[b"retry-after"] == b"17"
    key = "rl:general:u:user-a"
    assert fake.counters[key] == 3
    # 固定窗口只在首个请求设置一次过期
    assert fake.expires[key] == 60


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_in_process(monkeypatch):
    fake = _FakeRedis(fail=True)
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: fake)
    middleware = _build_middleware(max_requests=2)

    statuses = [(await _call(middleware, _scope(state={"user_id": "user-a"})))[0] for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert middleware._store  # 回落确实在进程内记账


@pytest.mark.asyncio
async def test_no_redis_configured_uses_in_process(monkeypatch):
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: None)
    middleware = _build_middleware(max_requests=1)

    assert (await _call(middleware, _scope(state={"user_id": "user-a"})))[0] == 200
    assert (await _call(middleware, _scope(state={"user_id": "user-a"})))[0] == 429


@pytest.mark.asyncio
async def test_exempt_paths_do_not_consume_budget(monkeypatch):
    monkeypatch.setattr(RateLimitMiddleware, "_redis_client", lambda self: None)
    middleware = _build_middleware(max_requests=1)

    for _ in range(5):
        status, _, _ = await _call(middleware, _scope(path="/metrics", method="GET"))
        assert status == 200
    assert (await _call(middleware, _scope(state={"user_id": "user-a"})))[0] == 200
