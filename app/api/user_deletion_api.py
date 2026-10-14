"""Administrator controlled, auditable user data deletion workflow."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.data.database import get_db_session
from app.security.access_control import require_admin_role
from app.security.audit import get_audit_logger
from app.services.user_data_deletion import (
    execute_user_deletion,
    preview_user_deletion,
    request_user_deletion,
)

router = APIRouter(prefix="/api/admin/user-deletions", tags=["用户数据删除-管理接口"])


class DeletionConfirmation(BaseModel):
    confirmation: str


def _admin_id(request: Request) -> str:
    require_admin_role(request)
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return str(user_id)


@router.get("/{user_id}/preview")
async def preview(request: Request, user_id: str):
    _admin_id(request)
    async with get_db_session() as db:
        return {"code": 0, "data": (await preview_user_deletion(db, user_id)).as_dict()}


@router.post("/{user_id}/request")
async def create_request(request: Request, user_id: str, body: DeletionConfirmation):
    admin_id = _admin_id(request)
    try:
        async with get_db_session() as db:
            result = await request_user_deletion(db, user_id=user_id, requested_by=admin_id, confirmation=body.confirmation)
        get_audit_logger().log_deletion(admin_id, "user_data_deletion_request", user_id, "管理员创建删除任务，等待执行")
        return {"code": 0, "data": result}
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
async def task_status(request: Request, task_id: str):
    _admin_id(request)
    from app.data.models import AsyncTask
    from sqlalchemy import select
    async with get_db_session() as db:
        task = await db.scalar(select(AsyncTask).where(AsyncTask.id == task_id, AsyncTask.task_type == "user_data_deletion"))
        if task is None:
            raise HTTPException(status_code=404, detail="删除任务不存在")
        return {"code": 0, "data": {"task_id": task.id, "status": task.status, "attempts": task.attempts, "result": task.result, "last_error": task.last_error}}


@router.post("/tasks/{task_id}/execute")
async def execute(request: Request, task_id: str, body: DeletionConfirmation):
    admin_id = _admin_id(request)
    if body.confirmation != "DELETE_USER_DATA":
        raise HTTPException(status_code=400, detail="需要二次确认：DELETE_USER_DATA")
    try:
        result = await execute_user_deletion(task_id, retry=True)
        get_audit_logger().log_deletion(admin_id, "user_data", result.get("user_id", ""), f"管理员执行删除任务，状态={result.get('status')}")
        return {"code": 0, "data": result}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
