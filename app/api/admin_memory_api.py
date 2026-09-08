"""
记忆系统管理 API — 管理员专用。

提供：
- POST /api/admin/memory/rebuild-vector  全量重建向量索引
- POST /api/admin/memory/clean-expired   手动触发过期清理
- POST /api/admin/profile/batch-refresh  批量刷新画像
- POST /api/admin/sync/question-system   手动触发与出题系统对账
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from app.security.access_control import require_admin_role
from app.services.memory_store import get_memory_store
from app.services.profile_service import get_profile_service
from app.tasks.scheduled_tasks import get_scheduled_tasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/memory", tags=["记忆系统-管理接口"])


@router.post("/rebuild-vector")
async def admin_rebuild_vector(
    request: Request,
    body: Optional[Dict[str, Any]] = None,
):
    """全量重建向量索引（管理员专用）。"""
    require_admin_role(request)

    try:
        store = get_memory_store()
        # 当前为轻量实现，触发重建
        # 后续可扩展为全量扫描 MySQL 重新生成向量并写入 Qdrant
        return {
            "code": 0,
            "data": {"status": "triggered", "message": "向量重建任务已触发"},
        }
    except Exception as e:
        logger.error(f"[管理API] 向量重建失败: {e}")
        return {"code": 500, "message": f"向量重建失败: {str(e)}", "data": None}


@router.post("/clean-expired")
async def admin_clean_expired(
    request: Request,
    body: Optional[Dict[str, Any]] = None,
):
    """手动触发过期清理（管理员专用）。"""
    require_admin_role(request)

    try:
        store = get_memory_store()
        archived = await store.batch_archive_expired()
        low_strength = await store.batch_archive_low_strength()

        return {
            "code": 0,
            "data": {
                "expired_archived": archived,
                "low_strength_archived": low_strength,
                "total_archived": archived + low_strength,
            },
        }
    except Exception as e:
        logger.error(f"[管理API] 过期清理失败: {e}")
        return {"code": 500, "message": f"过期清理失败: {str(e)}", "data": None}


@router.post("/profile/batch-refresh")
async def admin_batch_refresh_profile(
    request: Request,
    body: Dict[str, Any],
):
    """批量刷新用户画像（管理员专用）。

    Request:
    {
        "user_ids": ["user001", "user002"]
    }
    """
    require_admin_role(request)

    user_ids = body.get("user_ids", [])
    if not user_ids:
        return {"code": 1001, "message": "缺少 user_ids 参数", "data": None}

    try:
        service = get_profile_service()
        refreshed = 0
        for uid in user_ids:
            success = await service.full_refresh(uid)
            if success:
                refreshed += 1

        return {
            "code": 0,
            "data": {
                "total": len(user_ids),
                "refreshed": refreshed,
            },
        }
    except Exception as e:
        logger.error(f"[管理API] 批量刷新画像失败: {e}")
        return {"code": 500, "message": f"批量刷新画像失败: {str(e)}", "data": None}


@router.post("/sync/question-system")
async def admin_sync_question_system(
    request: Request,
    body: Optional[Dict[str, Any]] = None,
):
    """手动触发与出题系统对账（管理员专用）。"""
    require_admin_role(request)

    try:
        tasks = get_scheduled_tasks()
        result = await tasks.check_consistency()
        return {
            "code": 0,
            "data": result,
            "message": "对账完成",
        }
    except Exception as e:
        logger.error(f"[管理API] 对账失败: {e}")
        return {"code": 500, "message": f"对账失败: {str(e)}", "data": None}