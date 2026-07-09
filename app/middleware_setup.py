"""
FastAPI 中间件配置。

负责 CORS、安全头、速率限制、认证等中间件的配置与注册。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.config.middleware_config import middleware_config
from app.middleware.path_matcher import PathMatcher
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.auth_middleware import AuthenticationMiddleware


def setup_middleware(app: FastAPI):
    """配置并注册所有中间件。"""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Session-Id"],
        max_age=settings.CORS_MAX_AGE,
    )

    path_matcher = PathMatcher(
        static_paths=middleware_config.STATIC_PATHS,
        skip_paths=list(middleware_config.NO_AUTH_PATHS),
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