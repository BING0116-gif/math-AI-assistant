from typing import List, Set

from pydantic import Field
from pydantic_settings import BaseSettings


class MiddlewareConfig(BaseSettings):
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    RATE_LIMIT_MAX_REQUESTS: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")

    RATE_LIMIT_SKIP_PATHS: Set[str] = Field(
        default={
            "/api/admin/",
            # 心跳/轮询类高频请求：多标签页挂后台时会把全局限流预算吃光，
            # 导致真实页面加载被 429 误伤，故豁免。
            "/api/learning/activities/",  # 学习活动心跳/结束（POST .../{id}/heartbeat、/end）
            "/api/animations/jobs/",      # 动画任务状态轮询（前端每 2.5s 一次）
        },
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
            "/api/health/ready",
            "/api/recommend/health",
            "/api/internal/",
            "/",
            "/error_book",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics",
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
