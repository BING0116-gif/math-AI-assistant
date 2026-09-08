import logging
from typing import Set

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.auth import verify_access_token
from app.middleware.auth import get_user_by_id
from app.middleware.path_matcher import PathMatcher

logger = logging.getLogger(__name__)

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
        self._no_auth_paths = no_auth_paths if no_auth_paths is not None else set()
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

        try:
            current_user = await get_user_by_id(user_id)
        except Exception:
            logger.exception("认证用户查询失败")
            response = JSONResponse(
                status_code=503,
                content={"detail": "认证服务暂时不可用"},
            )
            await response(scope, receive, send)
            return

        if current_user is None or not current_user.is_active:
            response = JSONResponse(
                status_code=401,
                content={"detail": "用户不存在或已停用，请重新登录"},
            )
            await response(scope, receive, send)
            return

        request.state.user_id = str(current_user.id)
        request.state.current_user = current_user
        from app.observability import user_id_var
        context_token = user_id_var.set(str(current_user.id))
        try:
            await self.app(scope, receive, send)
        finally:
            user_id_var.reset(context_token)
