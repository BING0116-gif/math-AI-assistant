"""
应用生命周期管理。

负责 FastAPI 应用启动和关闭时的初始化与清理操作。
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from cryptography.fernet import Fernet

from app.config.settings import settings
from app.data.database import init_db, close_db, is_database_available
from app.services.ai_capability import is_ai_available
from app.services.cache import get_cache_manager
from app.middleware.auth import init_default_admin
from app.data.database import get_db_session
from app.services.knowledge_seed import seed_phase_one_calculus
from app.tasks.scheduled_tasks import get_scheduled_tasks

logger = logging.getLogger(__name__)

_INSECURE_JWT_SECRETS = {
    "math-ai-jwt-secret-must-be-overridden-in-production",
    "change-this-to-a-long-random-secret",
}
_INSECURE_ENCRYPTION_KEYS = {
    "",
    "changeme",
    "change-me",
    "change-this-encryption-key",
}
_INSECURE_ADMIN_PASSWORDS = {
    "admin",
    "admin123",
    "password",
    "changeme",
    "change-me",
    "change-this-password",
}


def validate_runtime_security() -> None:
    """Fail closed for every non-test runtime."""
    environment = settings.APP_ENV.strip().lower()
    if environment == "test":
        return
    secret = settings.JWT_SECRET_KEY or ""
    if secret in _INSECURE_JWT_SECRETS or len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be explicitly configured with at least 32 characters")
    if environment == "production":
        encryption_key = (settings.ENCRYPTION_KEY or "").strip()
        if encryption_key in _INSECURE_ENCRYPTION_KEYS:
            raise RuntimeError("ENCRYPTION_KEY must be explicitly configured in production")
        try:
            Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError):
            raise RuntimeError("ENCRYPTION_KEY must be a valid Fernet key in production") from None
        if settings.ALLOW_MOCK_PUBLISH:
            raise RuntimeError("ALLOW_MOCK_PUBLISH is forbidden in production")
        if settings.DEBUG:
            raise RuntimeError("DEBUG must be disabled in production")
        admin_password = (settings.ADMIN_PASSWORD or "").strip().lower()
        if admin_password in _INSECURE_ADMIN_PASSWORDS:
            raise RuntimeError("ADMIN_PASSWORD must not use a default or placeholder value")
    if settings.MEMORY_EMBEDDING_MODEL != settings.VECTOR_EMBEDDING_MODEL:
        logger.warning("MEMORY_EMBEDDING_MODEL 已弃用；题目与记忆统一使用 VECTOR_EMBEDDING_MODEL")
    if settings.MEMORY_QDRANT_VECTOR_SIZE != settings.VECTOR_SIZE:
        logger.warning("MEMORY_QDRANT_VECTOR_SIZE 已弃用；统一使用 VECTOR_SIZE")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理。"""
    validate_runtime_security()
    logger.info("正在初始化数据库...")
    await init_db()
    if not is_database_available():
        logger.warning(
            "数据库不可用，跳过课程目录初始化与默认管理员创建等依赖数据库的步骤；"
            "应用以降级模式运行（数据库相关功能暂不可用）"
        )
    else:
        logger.info("数据库初始化完成")
        async with get_db_session() as session:
            await seed_phase_one_calculus(session)
        logger.info("Phase 1 高等数学课程目录已就绪")

        # 初始化默认管理员账号
        await init_default_admin(settings.JWT_SECRET_KEY)

    # RAG 推荐系统初始化
    if settings.RAG_ENABLED:
        try:
            if settings.RAG_ENABLE_VECTOR_SEARCH:
                from app.services.vector_store import get_vector_store
                await get_vector_store()
                logger.info("向量数据库初始化完成")
        except Exception as e:
            logger.warning(f"向量数据库初始化失败: {e}")
        try:
            if settings.RAG_ENABLE_AI_EXPLANATION and is_ai_available():
                from app.services.llm_service import get_llm_service
                get_llm_service()
                logger.info("LLM服务初始化完成")
        except Exception as e:
            logger.warning(f"LLM服务初始化失败: {e}")

    cache_mgr = get_cache_manager()
    redis_url = settings.REDIS_URL
    if redis_url:
        await cache_mgr.initialize()

    scheduled_tasks = get_scheduled_tasks()
    try:
        scheduled_tasks.start_scheduler()
    except Exception as exc:
        logger.warning("定时任务启动失败（不影响 API 服务）: %s", exc)

    logger.info("应用启动完成")
    yield

    logger.info("正在关闭连接...")
    get_scheduled_tasks().stop_scheduler()
    await cache_mgr.close()
    await close_db()
    logger.info("连接已关闭")
