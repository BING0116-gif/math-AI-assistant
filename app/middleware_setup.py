"""
FastAPI 中间件配置。

负责 CORS、安全头、速率限制、认证、请求体大小限制等中间件的配置与注册。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

from app.config.settings import settings
from app.config.middleware_config import middleware_config
from app.middleware.path_matcher import PathMatcher
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.auth_middleware import AuthenticationMiddleware
from app.observability import ObservabilityMiddleware

# 请求体大小限制：文本 10MB，图片 5MB
MAX_TEXT_BODY_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_BODY_SIZE = 5 * 1024 * 1024  # 5MB


class RequestBodySizeMiddleware:
    """限制请求体大小，防止超大请求。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = 0
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"content-length":
                content_length = int(header_value)
                break

        if content_length > MAX_TEXT_BODY_SIZE:
            response = JSONResponse(
                status_code=413,
                content={"detail": "请求体过大，文本请求最大允许 10MB"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def setup_middleware(app: FastAPI):
    """配置并注册所有中间件。"""

    app.add_middleware(ObservabilityMiddleware)
    # 请求体大小限制
    app.add_middleware(RequestBodySizeMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Session-Id", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=settings.CORS_MAX_AGE,
    )

    path_matcher = PathMatcher(
        static_paths=middleware_config.STATIC_PATHS,
        skip_paths=list(middleware_config.NO_AUTH_PATHS),
        rate_limit_skip_paths=list(middleware_config.RATE_LIMIT_SKIP_PATHS),
    )

    app.add_middleware(
        SecurityHeadersMiddleware,
        debug=settings.DEBUG,
    )

    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=middleware_config.RATE_LIMIT_WINDOW_SECONDS,
        max_requests=middleware_config.RATE_LIMIT_MAX_REQUESTS,
        path_matcher=path_matcher,
    )

    app.add_middleware(
        AuthenticationMiddleware,
        jwt_secret_key=settings.JWT_SECRET_KEY,
        jwt_algorithm=settings.JWT_ALGORITHM,
        no_auth_paths=middleware_config.NO_AUTH_PATHS,
        path_matcher=path_matcher,
    )
