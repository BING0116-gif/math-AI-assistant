"""
Agent 和工具相关 API 路由。

包含 /api/agent/thought, /api/agent/stats, /api/tools, /api/health 端点。
"""

import logging
from fastapi import APIRouter, HTTPException

from app.config.settings import settings
from app.services.cache import get_cache_manager
from app.data.database import check_database_health, engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])


def get_agent():
    """获取全局 Agent 实例。"""
    from app.dependencies import get_agent as _get_agent
    return _get_agent()


def get_registry():
    """获取全局工具注册表。"""
    from app.dependencies import get_registry as _get_registry
    return _get_registry()


@router.get("/api/agent/thought/{session_id}")
async def get_thought_history(session_id: str):
    recorder = get_agent().get_thought_recorder()
    processes = recorder.get_session_processes(session_id, limit=10)
    return {
        "session_id": session_id,
        "processes": [p.to_dict() for p in processes],
        "total": len(processes),
    }


@router.get("/api/agent/stats")
async def get_agent_stats():
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

    overall = "healthy" if all(
        c.get("status") == "healthy" for c in checks.values()
    ) else "degraded"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


async def _check_migration_status() -> dict:
    """检查 Alembic 迁移状态。"""
    try:
        if engine is None:
            return {"status": "degraded", "error": "数据库未初始化"}
        from sqlalchemy import text as sa_text
        async with engine.connect() as conn:
            result = await conn.execute(sa_text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            if row:
                return {"status": "healthy", "version": row[0]}
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