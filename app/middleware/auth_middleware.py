import logging
from typing import Set

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.auth import verify_access_token
from app.middleware.path_matcher import PathMatcher

logger = logging.getLogger(__name__)

_DEFAULT_NO_AUTH_PATHS: Set[str] = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/recognize",
    "/api/error-book",
    "/api/tools",
    "/api/tools/stats",
    "/api/tools/search",
    "/api/tools/",
    "/api/agent/thought/",
    "/api/agent/stats",
    "/api/health",
    "/api/health/detailed",
    "/api/health/db",
    "/api/health/cache",
    "/api/recommend/health",
    "/",
    "/error_book",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class AuthenticationMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        jwt_secret_key: str,
        jwt_algorithm: str = "HS256",
        no_auth_paths: Set[str] | None = None,
        path_matcher: PathMatcher | None = None,
    ):
        self.app = app
        self._jwt_secret_key = jwt_secret_key
        self._jwt_algorithm = jwt_algorithm
        self._no_auth_paths = no_auth_paths or _DEFAULT_NO_AUTH_PATHS
        self._path_matcher = path_matcher or PathMatcher()

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        if path in self._no_auth_paths or self._path_matcher.should_skip_auth(request):
            await self.app(scope, receive, send)
            return

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            response = JSONResponse(
                status_code=401,
                content={"detail": "未提供认证令牌，请先登录"},
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:]
        user_id = verify_access_token(
            token, self._jwt_secret_key, self._jwt_algorithm
        )

        if user_id is None:
            response = JSONResponse(
                status_code=401,
                content={"detail": "认证令牌无效或已过期，请重新登录"},
            )
            await response(scope, receive, send)
            return

        request.state.user_id = user_id
        await self.app(scope, receive, send)
