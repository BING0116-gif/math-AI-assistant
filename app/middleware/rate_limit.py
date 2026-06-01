import logging
import time
from collections import defaultdict

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.path_matcher import PathMatcher

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        window_seconds: int = 60,
        max_requests: int = 30,
        path_matcher: PathMatcher | None = None,
    ):
        self.app = app
        self._window_seconds = window_seconds
        self._max_requests = max_requests
        self._path_matcher = path_matcher or PathMatcher()
        self._store: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup_time = time.time()

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if self._path_matcher.should_skip_rate_limit(request):
            await self.app(scope, receive, send)
            return

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        requests = self._store[client_ip]
        requests[:] = [t for t in requests if now - t < self._window_seconds]

        if len(requests) >= self._max_requests:
            response = JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
            )
            await response(scope, receive, send)
            return

        requests.append(now)

        if now - self._last_cleanup_time > 300:
            self._cleanup(now)

        await self.app(scope, receive, send)

    def _cleanup(self, now: float) -> None:
        self._last_cleanup_time = now
        expired_ips = [
            ip for ip, reqs in self._store.items()
            if not reqs or all(now - t > self._window_seconds for t in reqs)
        ]
        for ip in expired_ips:
            del self._store[ip]
