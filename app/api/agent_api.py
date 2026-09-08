"""
Agent 和工具相关 API 路由。

包含 /api/agent/thought, /api/agent/stats, /api/tools, /api/health 端点。
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.models.ai_unavailable import AIUnavailableResponse
from app.services.ai_capability import get_ai_capability, is_ai_available, raise_ai_unavailable
from app.services.cache import get_cache_manager
from app.data.database import check_database_health

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])


def _check_ai_available(capability: str) -> None:
    """检查 AI 是否可用，不可用时抛出结构化 503。"""
    if not is_ai_available():
        raise_ai_unavailable(capability)


def get_agent():
    """获取全局 Agent 实例。"""
    from app.dependencies import get_agent as _get_agent
    return _get_agent()


def get_registry():
    """获取全局工具注册表。"""
    from app.dependencies import get_registry as _get_registry
    return _get_registry()


@router.get("/api/agent/thought/{session_id}", responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def get_thought_history(session_id: str, request: Request):
    _check_ai_available("agent")
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    agent = get_agent()
    recorder = agent.get_thought_recorder()
    session_key = agent.session_key(str(user_id), session_id)
    processes = recorder.get_session_processes(session_key, limit=10)
    if not processes:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session_id,
        "processes": [p.to_dict() for p in processes],
        "total": len(processes),
    }


@router.get("/api/agent/stats", responses={
    503: {"description": "AI 功能不可用", "model": AIUnavailableResponse},
})
async def get_agent_stats():
    _check_ai_available("agent")
    recorder = get_agent().get_thought_recorder()
    return recorder.get_stats()


@router.get("/api/tools")
async def list_tools():
    tools = get_registry().list_tools()
    return {"tools": tools, "total": len(tools)}


@router.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    from tools import ToolNotFoundError
    try:
        tool = get_registry().get_tool(tool_name)
        return tool.get_info()
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"工具未注册: '{tool_name}'")


@router.get("/api/tools/stats")
async def get_tool_stats():
    return get_registry().get_execution_stats()


@router.get("/api/tools/search")
async def search_tools(capability: str):
    tools = get_registry().search_tools(capability)
    return {"capability": capability, "tools": tools}


@router.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "math-ai-agent-data",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
    }


@router.get("/api/health/detailed")
async def detailed_health():
    checks = {
        "database": await check_database_health(),
        "migration": await _check_migration_status(),
        "cache": _check_cache_health(),
        "disk_space": _check_disk_space(),
        "memory_usage": _check_memory_usage(),
    }
    from app.services.outbox import outbox_health
    checks["outbox"] = await outbox_health()
    if settings.RAG_ENABLED and settings.RAG_ENABLE_VECTOR_SEARCH:
        checks.update(await _check_vector_health())

    overall = "healthy" if all(
        c.get("status") == "healthy" for c in checks.values()
    ) else "degraded"

    # AI capability 状态
    ai_cap = get_ai_capability()

    return {
        "status": overall,
        "checks": checks,
        "ai": {
            "enabled": ai_cap.enabled_config,
            "configured": ai_cap.has_api_key,
            "available": ai_cap.available,
            "reason": ai_cap.reason,
        },
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


@router.get("/api/health/ready")
async def readiness_check():
    checks = {
        "database": await check_database_health(),
        "migration": await _check_migration_status(),
        "cache": await _check_cache_readiness(),
    }
    from app.services.outbox import outbox_health
    checks["outbox"] = await outbox_health()
    if settings.RAG_ENABLED and settings.RAG_ENABLE_VECTOR_SEARCH:
        checks.update(await _check_vector_health())
    ready = all(row.get("status") == "healthy" for row in checks.values())
    payload = {
        "status": "healthy" if ready else "degraded",
        "checks": checks,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


async def _check_cache_readiness() -> dict:
    try:
        cache = get_cache_manager()
        if cache.redis is None:
            return {"status": "degraded", "error": "Redis 未连接"}
        await cache.redis.ping()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}


async def _check_vector_health() -> dict:
    from sqlalchemy import func, select
    from app.data.database import get_db_session
    from app.data.models import Question
    from app.services.embedding_service import get_embedding_service

    embedding = get_embedding_service()
    result = {"embedding": embedding.health()}
    try:
        from app.services.vector_store import get_vector_store
        store = await get_vector_store()
        available = await store.check_availability()
        stats = await store.get_collection_stats()
        async with get_db_session() as db:
            expected = int(await db.scalar(select(func.count(Question.id)).where(
                Question.review_status == "published"
            )) or 0)
        actual = int(stats.get("total_documents", -1)) if stats.get("mode") == "qdrant" else -1
        healthy = available and stats.get("mode") == "qdrant" and actual == expected
        result["qdrant"] = {
            "status": "healthy" if healthy else "degraded",
            "collection": settings.QUESTION_QDRANT_COLLECTION,
            "sql_published": expected,
            "indexed": actual,
            "details": stats,
        }
    except Exception as exc:
        result["qdrant"] = {"status": "degraded", "error": str(exc)}
    return result


async def _check_migration_status() -> dict:
    """检查 Alembic 迁移状态。"""
    try:
        from app.data import database
        if database.engine is None:
            return {"status": "degraded", "error": "数据库未初始化"}
        from sqlalchemy import text as sa_text
        async with database.engine.connect() as conn:
            result = await conn.execute(sa_text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            if row:
                from alembic.config import Config
                from alembic.script import ScriptDirectory
                from pathlib import Path
                config = Config(str(Path(__file__).resolve().parents[1] / "data" / "alembic.ini"))
                head = ScriptDirectory.from_config(config).get_current_head()
                return {
                    "status": "healthy" if row[0] == head else "degraded",
                    "version": row[0],
                    "head": head,
                }
            return {"status": "degraded", "error": "未找到迁移版本"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


def _check_cache_health() -> dict:
    try:
        cache = get_cache_manager()
        cache_stats = cache.stats
        return {"status": "healthy", "stats": cache_stats}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


def _check_disk_space() -> dict:
    try:
        import psutil
        disk = psutil.disk_usage(".")
        percent = disk.percent
        if percent > 95:
            status = "critical"
        elif percent > 90:
            status = "warning"
        else:
            status = "healthy"
        return {
            "status": status,
            "used_percent": percent,
            "free_gb": round(disk.free / (1024**3), 2),
            "total_gb": round(disk.total / (1024**3), 2),
        }
    except ImportError:
        return {"status": "skipped", "message": "psutil 未安装"}


def _check_memory_usage() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "status": "healthy" if mem.percent < 90 else "warning",
            "used_percent": mem.percent,
            "available_mb": round(mem.available / (1024**2), 2),
            "total_gb": round(mem.total / (1024**3), 2),
        }
    except ImportError:
        return {"status": "skipped", "message": "psutil 未安装"}
