from typing import List, Set

from pydantic import Field
from pydantic_settings import BaseSettings


class MiddlewareConfig(BaseSettings):
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    RATE_LIMIT_MAX_REQUESTS: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")

    RATE_LIMIT_SKIP_PATHS: Set[str] = Field(
        default={"/api/admin/"},
        alias="RATE_LIMIT_SKIP_PATHS",
    )

    NO_AUTH_PATHS: Set[str] = Field(
        default={
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/refresh",
            "/api/tools",
            "/api/tools/stats",
            "/api/tools/search",
            "/api/tools/",
            "/api/agent/stats",
            "/api/health",
            "/api/health/detailed",
            "/api/health/db",
            "/api/health/cache",
            "/api/recommend/health",
            "/api/internal/",
            "/",
            "/error_book",
            "/docs",
            "/redoc",
            "/openapi.json",
        },
        alias="NO_AUTH_PATHS",
    )

    STATIC_PATHS: List[str] = Field(
        default=["/static", "/assets", "/@vite", "/frontend"],
        alias="STATIC_PATHS",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


middleware_config = MiddlewareConfig()
