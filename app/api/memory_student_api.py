"""用户可控记忆 API(路线图 6.5,4-E)。

学生主权:查看/确认/纠正/删除/导出本人记忆。全部按 user_id 隔离 + 学生认证;
删除为软删(SQL+Qdrant 同步);纠正走 superseded 链;导出仅本人数据(合规 10.7)。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.student_contracts import STUDENT_API_RESPONSES, StudentEnvelope
from app.security.audit import get_audit_logger
from app.services.memory_store import get_memory_store

router = APIRouter(prefix="/api/memory", tags=["记忆系统-学生主权"])


def _user_id(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)


class MemoryItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    memory_type: str
    memory_kind: str
    category: str = ""
    content: str
    status: str
    confidence: float
    memory_strength: float
    conflict_status: str = "none"
    superseded_by: int | None = None
    created_at: int
    last_confirmed_at: int | None = None
    expire_at: int | None = None


class MemoryCorrectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrected_content: str = Field(min_length=1, max_length=4000)


def _memory_envelope(items: list[dict[str, Any]] | dict[str, Any]) -> StudentEnvelope:
    return {"code": 0, "data": items}


@router.get("", responses={**STUDENT_API_RESPONSES, 200: {"model": StudentEnvelope[list[MemoryItemOut]]}})
async def list_my_memories(
    http_request: Request,
    status: str = Query("active", pattern="^(active|pending|archived|deleted)$"),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """查看本人记忆:内容、kind、置信度、来源时间、状态(6.5)。"""
    user_id = _user_id(http_request)
    items = await get_memory_store().list_user_memories(
        user_id,
        status="" if include_deleted else status,
        include_deleted=include_deleted,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return _memory_envelope(items)


@router.post("/{memory_id}/confirm", responses=STUDENT_API_RESPONSES)
async def confirm_memory(memory_id: int, http_request: Request):
    """确认记忆:置信度 → 0.9 并记录确认时间(幂等)。"""
    user_id = _user_id(http_request)
    if not await get_memory_store().confirm_memory(user_id, memory_id):
        raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND", "message": "记忆不存在或不属于当前用户"})
    get_audit_logger().log_modification(
        user_id, "memory", str(memory_id),
        old_value={}, new_value={"confirmed": True}, changed_fields=["confidence", "last_confirmed_at"],
    )
    return {"code": 0, "data": {"memory_id": memory_id, "confirmed": True}}


@router.post("/{memory_id}/correct", responses=STUDENT_API_RESPONSES)
async def correct_memory(memory_id: int, body: MemoryCorrectRequest, http_request: Request):
    """纠正记忆:生成新记忆(confidence=0.95),旧记忆 superseded 链下线(幂等)。"""
    user_id = _user_id(http_request)
    new_id = await get_memory_store().correct_memory(user_id, memory_id, body.corrected_content)
    if new_id is None:
        raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND", "message": "记忆不存在或不属于当前用户"})
    get_audit_logger().log_modification(
        user_id, "memory", str(memory_id),
        old_value={}, new_value={"superseded_by": new_id}, changed_fields=["superseded_by", "conflict_status"],
    )
    return {"code": 0, "data": {"memory_id": memory_id, "new_memory_id": new_id, "corrected": True}}


@router.delete("/{memory_id}", responses=STUDENT_API_RESPONSES)
async def delete_memory(memory_id: int, http_request: Request):
    """删除本人记忆:软删 + SQL/Qdrant 同步下线(幂等,重复删除返回成功)。"""
    user_id = _user_id(http_request)
    deleted = await get_memory_store().delete_memory_owned(user_id, memory_id)
    if not deleted:
        # 已删除过(幂等)或不存在——不区分给普通用户,避免探测他人资源
        raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND", "message": "记忆不存在或不属于当前用户"})
    get_audit_logger().log_deletion(user_id, "memory", str(memory_id), reason="user self-service delete")
    return {"code": 0, "data": {"memory_id": memory_id, "deleted": True}}


@router.get("/export", responses={**STUDENT_API_RESPONSES, 200: {"model": StudentEnvelope[list[MemoryItemOut]]}})
async def export_my_memories(http_request: Request):
    """导出本人全部未删除记忆(JSON,合规联动 10.7)。"""
    user_id = _user_id(http_request)
    items = await get_memory_store().list_user_memories(
        user_id, status="", include_deleted=False, offset=0, limit=200
    )
    get_audit_logger().log_export(user_id, "memory", len(items))
    return _memory_envelope(items)
