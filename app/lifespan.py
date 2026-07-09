"""
应用生命周期管理。

负责 FastAPI 应用启动和关闭时的初始化与清理操作。
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config.settings import settings
from app.data.database import init_db, close_db
from app.services.cache import get_cache_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理。"""
    logger.info("正在初始化数据库...")
    await init_db()
    logger.info("数据库初始化完成")

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
            if settings.RAG_ENABLE_AI_EXPLANATION:
                from app.services.llm_service import get_llm_service
                get_llm_service()
                logger.info("LLM服务初始化完成")
        except Exception as e:
            logger.warning(f"LLM服务初始化失败: {e}")

    cache_mgr = get_cache_manager()
    redis_url = settings.REDIS_URL
    if redis_url:
        await cache_mgr.initialize()

    logger.info("应用启动完成")
    yield

    logger.info("正在关闭连接...")
    await cache_mgr.close()
    await close_db()
    logger.info("连接已关闭")