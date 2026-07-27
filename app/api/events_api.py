"""
出题系统事件接收 API。

提供事件接口：
- POST /api/internal/event/question-finish  单题作答完成事件
- POST /api/internal/event/mastery-update   知识点掌握度更新事件
- POST /api/internal/event/chapter-complete 章节完成事件
- POST /api/internal/event/question-change  题目基础信息变更事件
- GET  /api/internal/sync/check-consistency 跨系统数据一致性对账
"""

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Header

from app.adapters.question_system.events import EventDispatcher
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["记忆系统-事件接口"])

# 事件幂等性缓存（内存 + TTL）
_event_idempotency: Dict[str, float] = {}
IDEMPOTENCY_TTL = 86400  # 24 小时


def _check_event_idempotency(event_id: str) -> bool:
    """检查事件幂等性，已处理过的事件返回 True。"""
    now = time.time()
    # 清理过期记录
    expired = [k for k, v in _event_idempotency.items() if now - v > IDEMPOTENCY_TTL]
    for k in expired:
        _event_idempotency.pop(k, None)

    if event_id in _event_idempotency:
        return True
    _event_idempotency[event_id] = now
    return False


def _verify_event_api_key(api_key: Optional[str] = None) -> bool:
    """校验事件接口 API Key。"""
    if not settings.QUESTION_SYSTEM_API_KEY:
        # 未配置 API Key 时跳过校验（开发模式）
        return True
    return api_key == settings.QUESTION_SYSTEM_API_KEY


dispatcher = EventDispatcher()


@router.post("/event/question-finish")
async def event_question_finish(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """单题作答完成事件。

    出题系统推送学生完成一道题目的结果。
    """
    if not _verify_event_api_key(x_api_key):
        return {"code": 2003, "message": "API Key 无效", "data": None}

    event_id = body.get("event_id", "")
    if event_id and _check_event_idempotency(event_id):
        return {"code": 0, "message": "事件已处理（幂等）", "data": None}

    try:
        result = await dispatcher.dispatch("question-finish", body)
        return result
    except Exception as e:
        logger.error(f"[事件API] question-finish 处理失败: {e}")
        return {"code": 500, "message": f"处理失败: {str(e)}", "data": None}


@router.post("/event/mastery-update")
async def event_mastery_update(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """知识点掌握度更新事件。"""
    if not _verify_event_api_key(x_api_key):
        return {"code": 2003, "message": "API Key 无效", "data": None}

    event_id = body.get("event_id", "")
    if event_id and _check_event_idempotency(event_id):
        return {"code": 0, "message": "事件已处理（幂等）", "data": None}

    try:
        result = await dispatcher.dispatch("mastery-update", body)
        return result
    except Exception as e:
        logger.error(f"[事件API] mastery-update 处理失败: {e}")
        return {"code": 500, "message": f"处理失败: {str(e)}", "data": None}


@router.post("/event/chapter-complete")
async def event_chapter_complete(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """章节完成事件。"""
    if not _verify_event_api_key(x_api_key):
        return {"code": 2003, "message": "API Key 无效", "data": None}

    event_id = body.get("event_id", "")
    if event_id and _check_event_idempotency(event_id):
        return {"code": 0, "message": "事件已处理（幂等）", "data": None}

    try:
        result = await dispatcher.dispatch("chapter-complete", body)
        return result
    except Exception as e:
        logger.error(f"[事件API] chapter-complete 处理失败: {e}")
        return {"code": 500, "message": f"处理失败: {str(e)}", "data": None}


@router.post("/event/question-change")
async def event_question_change(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """题目基础信息变更事件。"""
    if not _verify_event_api_key(x_api_key):
        return {"code": 2003, "message": "API Key 无效", "data": None}

    event_id = body.get("event_id", "")
    if event_id and _check_event_idempotency(event_id):
        return {"code": 0, "message": "事件已处理（幂等）", "data": None}

    try:
        result = await dispatcher.dispatch("question-change", body)
        return result
    except Exception as e:
        logger.error(f"[事件API] question-change 处理失败: {e}")
        return {"code": 500, "message": f"处理失败: {str(e)}", "data": None}


@router.get("/sync/check-consistency")
async def check_consistency(
    request: Request,
    date: str = "",
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """跨系统数据一致性对账。"""
    if not _verify_event_api_key(x_api_key):
        return {"code": 2003, "message": "API Key 无效", "data": None}

    try:
        from app.tasks.scheduled_tasks import get_scheduled_tasks
        tasks = get_scheduled_tasks()
        result = await tasks.check_consistency()
        return {
            "code": 0,
            "data": {
                "total_memories": result.get("checked", 0),
                "invalid_source_count": result.get("archived", 0),
                "fixed_count": result.get("archived", 0),
                "details": [],
            },
        }
    except Exception as e:
        logger.error(f"[事件API] 对账失败: {e}")
        return {"code": 500, "message": f"对账失败: {str(e)}", "data": None}