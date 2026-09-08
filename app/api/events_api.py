"""
出题系统事件接收 API。

提供事件接口：
- POST /api/internal/event/question-finish  单题作答完成事件
- POST /api/internal/event/mastery-update   知识点掌握度更新事件
- POST /api/internal/event/chapter-complete 章节完成事件
- POST /api/internal/event/question-change  题目基础信息变更事件
- GET  /api/internal/sync/check-consistency 跨系统数据一致性对账
"""

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Header
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.question_system.events import EventDispatcher
from app.data.database import get_db_session
from app.data.models import EventIdempotency
from app.security.access_control import require_internal_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["记忆系统-事件接口"])

async def _claim_event(event_id: str, event_type: str) -> bool:
    """原子取得事件处理权；唯一键冲突表示已有处理者。"""
    if not event_id:
        return True
    try:
        async with get_db_session() as session:
            session.add(
                EventIdempotency(
                    event_id=event_id,
                    event_type=event_type,
                    processed_at=int(time.time()),
                    status="processing",
                )
            )
            await session.flush()
        return True
    except IntegrityError:
        # 失败事件允许一个调用者原子地重新取得处理权。
        async with get_db_session() as session:
            result = await session.execute(
                update(EventIdempotency)
                .where(
                    EventIdempotency.event_id == event_id,
                    EventIdempotency.status == "failed",
                )
                .values(
                    event_type=event_type,
                    processed_at=int(time.time()),
                    status="processing",
                )
            )
            return result.rowcount == 1


async def _set_event_status(event_id: str, status: str) -> None:
    if not event_id:
        return
    async with get_db_session() as session:
        await session.execute(
            update(EventIdempotency)
            .where(EventIdempotency.event_id == event_id)
            .values(status=status, processed_at=int(time.time()))
        )


dispatcher = EventDispatcher()


async def _dispatch_idempotent(event_type: str, body: Dict[str, Any]):
    event_id = str(body.get("event_id", "")).strip()
    if event_id and not await _claim_event(event_id, event_type):
        return {"code": 0, "message": "事件已处理（幂等）", "data": None}
    try:
        result = await dispatcher.dispatch(event_type, body)
        await _set_event_status(event_id, "processed")
        return result
    except Exception as e:
        await _set_event_status(event_id, "failed")
        logger.error("[事件API] %s 处理失败: %s", event_type, e)
        return {"code": 500, "message": f"处理失败: {str(e)}", "data": None}


@router.post("/event/question-finish")
async def event_question_finish(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """单题作答完成事件。

    出题系统推送学生完成一道题目的结果。
    """
    require_internal_auth(request)

    return await _dispatch_idempotent("question-finish", body)


@router.post("/event/mastery-update")
async def event_mastery_update(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """知识点掌握度更新事件。"""
    require_internal_auth(request)

    return await _dispatch_idempotent("mastery-update", body)


@router.post("/event/chapter-complete")
async def event_chapter_complete(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """章节完成事件。"""
    require_internal_auth(request)

    return await _dispatch_idempotent("chapter-complete", body)


@router.post("/event/question-change")
async def event_question_change(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """题目基础信息变更事件。"""
    require_internal_auth(request)

    return await _dispatch_idempotent("question-change", body)


@router.get("/sync/check-consistency")
async def check_consistency(
    request: Request,
    date: str = "",
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """跨系统数据一致性对账。"""
    require_internal_auth(request)

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
