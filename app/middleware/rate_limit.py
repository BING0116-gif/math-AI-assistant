"""限流中间件：Redis 固定窗口优先 + 进程内滑动窗口兜底。

两处关键修正：

1. **桶键**：不再使用 ``request.client.host``。生产拓扑下它是 nginx 容器 IP，
   所有学生共用一个预算，单用户开几个标签页就能触发全站 429。现在已认证请求按
   ``u:<user_id>`` 计数，未认证按解析后的真实客户端 IP 计数。
2. **分桶预算**：``/api/auth/login|register`` 走独立的更严预算（原先因 NO_AUTH
   与限流耦合而完全不受限），账户锁定逻辑因此才有意义。

Redis 不可用（未初始化、连接异常、测试环境）时回落到进程内实现；此时多 worker
预算不共享，属已知降级，详见 docs/STATUS.md。
"""

import logging
import math
import time
from collections import defaultdict

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.client_identity import resolve_client_ip, resolve_rate_limit_key
from app.middleware.path_matcher import (
    BUCKET_AUTH,
    BUCKET_AUTH_LOGIN,
    BUCKET_GENERAL,
    PathMatcher,
)
from app.observability import RATE_LIMIT_REJECTIONS

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "rl"
# 口令类桶永远按 IP 计数：登录成功前没有 user_id，也不能让攻击者通过附带
# 一个合法 token 来"换桶"绕过爆破预算。
_IP_KEYED_BUCKETS = (BUCKET_AUTH_LOGIN, BUCKET_AUTH)


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        window_seconds: int = 60,
        max_requests: int = 30,
        path_matcher: PathMatcher | None = None,
        bucket_limits: dict[str, int] | None = None,
    ):
        self.app = app
        self._window_seconds = window_seconds
        self._max_requests = max_requests
        self._path_matcher = path_matcher or PathMatcher()
        self._store: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup_time = time.time()
        self._bucket_limits: dict[str, int] = {
            BUCKET_GENERAL: max_requests,
            BUCKET_AUTH: max(1, min(10, max_requests)),
            BUCKET_AUTH_LOGIN: max(1, min(5, max_requests)),
        }
        if bucket_limits:
            self._bucket_limits.update({k: int(v) for k, v in bucket_limits.items() if int(v) > 0})
        self._redis_degraded_logged = False

    def _limit_for(self, bucket: str) -> int:
        return self._bucket_limits.get(bucket, self._max_requests)

    def _identity(self, request: Request, bucket: str) -> str:
        if bucket in _IP_KEYED_BUCKETS:
            return f"ip:{resolve_client_ip(request)}"
        return resolve_rate_limit_key(request)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if self._path_matcher.should_skip_rate_limit(request):
            await self.app(scope, receive, send)
            return

        bucket = self._path_matcher.rate_limit_bucket(request.url.path)
        identity = self._identity(request, bucket)
        limit = self._limit_for(bucket)
        now = time.time()

        used, retry_after = await self._consume(bucket, identity, limit, now)

        if used > limit:
            RATE_LIMIT_REJECTIONS.labels(bucket).inc()
            logger.info(
                "限流拒绝",
                extra={"operation": "rate_limit", "detail": f"bucket={bucket}"},
            )
            response = JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(max(1, int(math.ceil(retry_after))))},
            )
            await response(scope, receive, send)
            return

        if now - self._last_cleanup_time > 300:
            self._cleanup(now)

        await self.app(scope, receive, send)

    async def _consume(self, bucket: str, identity: str, limit: int, now: float) -> tuple[int, float]:
        """返回 (当前窗口已用次数, 距窗口结束的等待秒数)。超限判定由调用方完成。"""
        redis = self._redis_client()
        if redis is not None:
            try:
                return await self._consume_redis(redis, bucket, identity, limit)
            except Exception as exc:  # Redis 抖动不应放大成 500
                if not self._redis_degraded_logged:
                    self._redis_degraded_logged = True
                    logger.warning(f"限流 Redis 不可用，回落进程内计数: {exc}")
                else:
                    logger.debug(f"限流 Redis 不可用，回落进程内计数: {exc}")
        return self._consume_local(bucket, identity, limit, now)

    def _redis_client(self):
        # get_cache_manager() 是同步单例；lifespan 里 initialize() 之前 redis 为 None。
        from app.services.cache import get_cache_manager

        try:
            return get_cache_manager().redis
        except Exception:
            return None

    async def _consume_redis(self, redis, bucket: str, identity: str, limit: int) -> tuple[int, float]:
        key = f"{_REDIS_PREFIX}:{bucket}:{identity}"
        used = int(await redis.incr(key))
        if used == 1:
            # 只在窗口首个请求上设置过期，避免每请求一次额外往返。
            await redis.expire(key, self._window_seconds)
        if used <= limit:
            return used, float(self._window_seconds)
        ttl = await redis.ttl(key)
        return used, float(ttl) if ttl and ttl > 0 else float(self._window_seconds)

    def _consume_local(self, bucket: str, identity: str, limit: int, now: float) -> tuple[int, float]:
        key = f"{bucket}:{identity}"
        requests = self._store[key]
        requests[:] = [t for t in requests if now - t < self._window_seconds]
        used = len(requests)
        if used >= limit:
            oldest = requests[0] if requests else now
            wait = self._window_seconds - (now - oldest)
            return used + 1, max(1.0, wait)
        requests.append(now)
        return used + 1, float(self._window_seconds)

    def _cleanup(self, now: float) -> None:
        self._last_cleanup_time = now
        expired_keys = [
            key for key, reqs in self._store.items()
            if not reqs or all(now - t >= self._window_seconds for t in reqs)
        ]
        for key in expired_keys:
            del self._store[key]
