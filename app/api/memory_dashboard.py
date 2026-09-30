"""
记忆系统可视化 Dashboard API。

提供：
- GET /api/dashboard/memory/stats      记忆系统统计概览
- GET /api/dashboard/memory/user/{id}  用户记忆详情
- GET /api/dashboard/memory/timeline   记忆时间线
"""

import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.memory_store import get_memory_store
from app.services.profile_service import get_profile_service
from app.security.access_control import require_admin_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard/memory", tags=["记忆系统-Dashboard"])

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)
_MEMORY_TYPE_CLASSES = {
    "error": "type-error",
    "conversation": "type-conversation",
    "milestone": "type-milestone",
    "profile": "type-profile",
}


def _render_template(name: str, **context: Any) -> str:
    return _templates.get_template(name).render(**context)


def _percentage(value: Any) -> int:
    """Return a bounded percentage safe for an inline width declaration."""
    try:
        return max(0, min(100, int(float(value or 0) * 100)))
    except (TypeError, ValueError, OverflowError):
        return 0


@router.get("/stats", response_class=HTMLResponse)
async def dashboard_stats(request: Request):
    """记忆系统统计概览（HTML 页面）。"""
    require_admin_role(request)
    store = get_memory_store()

    stats = await _get_system_stats(store)
    recent_memories, recent_error = await _get_recent_memories()
    profiles, profiles_error = await _get_user_profiles()
    page = _render_template(
        "memory_dashboard/stats.html",
        stats=stats,
        stat_cards=[
            ("总记忆数", "total_memories", ""),
            ("活跃用户", "active_users", ""),
            ("错题记忆", "error_count", "info"),
            ("对话记忆", "conversation_count", "info"),
            ("里程碑", "milestone_count", ""),
            ("已归档", "archived_count", "warning"),
        ],
        recent_memories=recent_memories,
        recent_error=recent_error,
        profiles=profiles,
        profiles_error=profiles_error,
        updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    return HTMLResponse(content=page)

@router.get("/user/{user_id}", response_class=HTMLResponse)
async def dashboard_user(request: Request, user_id: str):
    """单个用户的记忆详情页面。"""
    require_admin_role(request)
    store = get_memory_store()
    profile_service = get_profile_service()

    # 获取用户记忆
    memories, total = await store.get_user_memories(
        user_id=user_id,
        limit=50,
    )

    # 获取用户画像
    profile = await profile_service.get_profile(user_id)

    page = _render_template(
        "memory_dashboard/user.html",
        user_id=user_id,
        summary=profile.get("summary_text", "暂无画像数据"),
        total=total,
        memories=[_memory_view(memory) for memory in memories],
    )
    return HTMLResponse(content=page)

@router.get("/timeline")
async def dashboard_timeline(
    request: Request,
    user_id: str = "",
    limit: int = 20,
):
    require_admin_role(request)
    """记忆时间线（JSON API）。"""
    store = get_memory_store()

    if user_id:
        memories, total = await store.get_user_memories(
            user_id=user_id,
            limit=limit,
        )
    else:
        memories = []
        total = 0

    return {
        "code": 0,
        "data": {
            "memories": memories,
            "total": total,
        },
    }


# ============================================================================
# 辅助函数
# ============================================================================

async def _get_system_stats(store) -> Dict[str, int]:
    """获取系统统计数据。"""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            # 总记忆数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories"))
            row = result.fetchone()
            total = row._mapping["cnt"] if row else 0

            # 活跃用户数
            result = await db.execute(sa_text("SELECT COUNT(DISTINCT user_id) as cnt FROM memories WHERE status = 'active'"))
            row = result.fetchone()
            active_users = row._mapping["cnt"] if row else 0

            # 错题数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'error' AND status = 'active'"))
            row = result.fetchone()
            error_count = row._mapping["cnt"] if row else 0

            # 对话数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'conversation' AND status = 'active'"))
            row = result.fetchone()
            conv_count = row._mapping["cnt"] if row else 0

            # 里程碑数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'milestone' AND status = 'active'"))
            row = result.fetchone()
            milestone_count = row._mapping["cnt"] if row else 0

            # 归档数
            result = await db.execute(sa_text("SELECT COUNT(*) as cnt FROM memories WHERE status = 'archived'"))
            row = result.fetchone()
            archived_count = row._mapping["cnt"] if row else 0

        return {
            "total_memories": total,
            "active_users": active_users,
            "error_count": error_count,
            "conversation_count": conv_count,
            "milestone_count": milestone_count,
            "archived_count": archived_count,
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return {
            "total_memories": 0,
            "active_users": 0,
            "error_count": 0,
            "conversation_count": 0,
            "milestone_count": 0,
            "archived_count": 0,
        }


def _memory_view(memory: Any) -> Dict[str, Any]:
    memory_type = str(memory.get("memory_type", "unknown") or "unknown")
    try:
        importance = float(memory.get("importance", 0) or 0)
        if not math.isfinite(importance):
            importance = 0.0
    except (TypeError, ValueError, OverflowError):
        importance = 0.0
    return {
        "id": memory.get("id", ""),
        "user_id": memory.get("user_id", ""),
        "memory_type": memory_type,
        "type_class": _MEMORY_TYPE_CLASSES.get(memory_type, "type-unknown"),
        "high_category": memory.get("high_category", ""),
        "category": memory.get("category", ""),
        "summary": str(memory.get("embedding_summary") or "")[:100],
        "importance": importance,
        "strength_pct": _percentage(memory.get("memory_strength", 0.5)),
        "status": memory.get("status", ""),
    }


async def _get_recent_memories() -> tuple[List[Dict[str, Any]], bool]:
    """Load recent memory view models; the boolean signals a read failure."""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            result = await db.execute(sa_text("""
                SELECT id, user_id, memory_type, high_category, category,
                       embedding_summary, importance, memory_strength, created_at, status
                FROM memories
                ORDER BY created_at DESC
                LIMIT 10
            """))
            return [_memory_view(row._mapping) for row in result.fetchall()], False
    except Exception:
        logger.exception("获取最近记忆失败")
        return [], True


async def _get_user_profiles() -> tuple[List[Dict[str, Any]], bool]:
    """Load profile overview view models; the boolean signals a read failure."""
    try:
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text

        async with get_db_session() as db:
            result = await db.execute(sa_text("""
                SELECT user_id, summary_text, version, updated_at
                FROM user_profiles
                ORDER BY updated_at DESC
                LIMIT 5
            """))
            profiles = [{
                "user_id": row._mapping["user_id"],
                "version": row._mapping["version"],
                "summary": str(row._mapping["summary_text"] or "暂无摘要")[:150],
            } for row in result.fetchall()]
            return profiles, False
    except Exception:
        logger.exception("获取用户画像概览失败")
        return [], True


def _render_user_memories(memories: List[Dict]) -> str:
    """Compatibility helper backed by the same autoescaped item template."""
    return _render_template(
        "memory_dashboard/memory_items.html",
        memories=[_memory_view(memory) for memory in memories],
    )
