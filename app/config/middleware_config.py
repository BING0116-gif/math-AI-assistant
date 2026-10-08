from typing import List, Set

from pydantic import Field
from pydantic_settings import BaseSettings


class MiddlewareConfig(BaseSettings):
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    RATE_LIMIT_MAX_REQUESTS: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")
    # 口令类端点（login/register）的每 IP 更严预算：原先 NO_AUTH 路径同时豁免限流，
    # 导致登录可被无限暴力尝试。
    RATE_LIMIT_AUTH_LOGIN_PER_MINUTE: int = Field(
        default=5, alias="RATE_LIMIT_AUTH_LOGIN_PER_MINUTE"
    )
    # 其余认证端点（refresh 等）的每 IP 预算。
    RATE_LIMIT_AUTH_PER_MINUTE: int = Field(
        default=10, alias="RATE_LIMIT_AUTH_PER_MINUTE"
    )

    RATE_LIMIT_SKIP_PATHS: Set[str] = Field(
        default={
            "/api/admin/",
            # 心跳/轮询类高频请求：多标签页挂后台时会把全局限流预算吃光，
            # 导致真实页面加载被 429 误伤，故豁免。
            "/api/learning/activities/",  # 学习活动心跳/结束（POST .../{id}/heartbeat、/end）
            "/api/animations/jobs/",      # 动画任务状态轮询（前端每 2.5s 一次）
            # 以下原本靠 NO_AUTH_PATHS 间接豁免限流；NO_AUTH 与限流解耦后必须显式列出，
            # 否则 Prometheus 抓取与健康探针会被限掉。
            "/api/health",
            "/api/recommend/health",
            "/api/internal/",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/tools/",
        },
        alias="RATE_LIMIT_SKIP_PATHS",
    )

    # 无论其它规则如何，这些路径必限流（优先于 RATE_LIMIT_SKIP_PATHS）。
    RATE_LIMIT_ALWAYS_PATHS: Set[str] = Field(
        default={
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/refresh",
        },
        alias="RATE_LIMIT_ALWAYS_PATHS",
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
