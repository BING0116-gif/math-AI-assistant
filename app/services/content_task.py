"""Content task service（P0-1/2）：DB 持久化任务表 + 独立 Worker 的核心操作。

任务状态机：
    pending → running → succeeded / partially_succeeded / failed / cancelled
    running 失败且可重试 → retrying（next_run_at 到期）→ running

多 Worker 安全：claim 采用条件 UPDATE（status ∈ {pending, retrying} 且 next_run_at 到期），
同一任务只会被一个 Worker 认领（rowcount==1 判定）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select, update

from app.data.database import get_db_session
from app.data.models import ContentTask

logger = logging.getLogger(__name__)

# 任务类型
KIND_IMPORT_PARSE = "import_parse"
KIND_AI_BATCH_ANALYZE = "ai_batch_analyze"

# 状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_RETRYING = "retrying"
STATUS_SUCCEEDED = "succeeded"
STATUS_PARTIAL = "partially_succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_CLAIMABLE = (STATUS_PENDING, STATUS_RETRYING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(retry_count: int) -> int:
    """指数退避：10s / 20s / 40s ... 上限 300s。"""
    return min(300, 10 * (2 ** max(0, retry_count - 1)))


class TaskCancelled(Exception):
    """任务被取消（Worker 内部中断信号）。"""


# ── 入队 / 查询 ──
async def enqueue_task(
    kind: str,
    ref_id: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    max_retries: int = 0,
    task_id: Optional[str] = None,
) -> ContentTask:
    task = ContentTask(
        id=task_id or _new_task_id(kind),
        kind=kind,
        ref_id=ref_id,
        status=STATUS_PENDING,
        payload=payload or {},
        max_retries=max_retries,
    )
    async with get_db_session() as db:
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task


def _new_task_id(kind: str) -> str:
    import uuid
    prefix = {"import_parse": "imp-", "ai_batch_analyze": "bat-"}.get(kind, "task-")
    return f"{prefix}{uuid.uuid4().hex[:24]}"


async def get_task(task_id: str) -> Optional[ContentTask]:
    async with get_db_session() as db:
        return await db.get(ContentTask, task_id)


async def list_tasks(kind: Optional[str] = None, limit: int = 50) -> List[ContentTask]:
    stmt = select(ContentTask).order_by(ContentTask.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(ContentTask.kind == kind)
    async with get_db_session() as db:
        return list((await db.execute(stmt)).scalars().all())


# ── Worker 认领 / 进度 / 完成 ──
async def claim_next_task(worker_id: str) -> Optional[ContentTask]:
    """认领下一个可执行任务（pending / retrying 且到期）。多 Worker 安全。"""
    now = _now()
    async with get_db_session() as db:
        candidates = (
            await db.execute(
                select(ContentTask.id)
                .where(ContentTask.status.in_(_CLAIMABLE))
                .where(or_(ContentTask.next_run_at.is_(None), ContentTask.next_run_at <= now))
                .order_by(ContentTask.created_at.asc())
                .limit(20)
            )
        ).scalars().all()
        for tid in candidates:
            res = await db.execute(
                update(ContentTask)
                .where(ContentTask.id == tid, ContentTask.status.in_(_CLAIMABLE))
                .values(
                    status=STATUS_RUNNING,
                    worker_id=worker_id,
                    started_at=now,
                    heartbeat_at=now,
                    updated_at=now,
                )
            )
            if res.rowcount == 1:
                return await db.get(ContentTask, tid)
        return None


async def touch_heartbeat(task_id: str, worker_id: str) -> None:
    async with get_db_session() as db:
        await db.execute(
            update(ContentTask)
            .where(ContentTask.id == task_id, ContentTask.status == STATUS_RUNNING)
            .values(heartbeat_at=_now(), updated_at=_now())
        )
        await db.commit()


async def update_progress(task_id: str, **fields: Any) -> None:
    async with get_db_session() as db:
        task = await db.get(ContentTask, task_id)
        if task is None:
            return
        progress = dict(task.progress or {})
        progress.update(fields)
        task.progress = progress
        task.heartbeat_at = _now()
        task.updated_at = _now()
        await db.commit()


async def complete_task(
    task_id: str,
    status: str,
    *,
    progress: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    async with get_db_session() as db:
        task = await db.get(ContentTask, task_id)
        if task is None or task.status != STATUS_RUNNING:
            return
        if progress:
            merged = dict(task.progress or {})
            merged.update(progress)
            task.progress = merged
        task.status = status
        task.error_code = error_code
        task.error_message = error_message
        task.completed_at = _now()
        task.updated_at = _now()
        await db.commit()


async def fail_task(task_id: str, code: str, message: str) -> None:
    """运行失败：可重试 → retrying（退避后再次认领）；否则 failed。"""
    async with get_db_session() as db:
        task = await db.get(ContentTask, task_id)
        if task is None or task.status != STATUS_RUNNING:
            return
        if task.retry_count < task.max_retries:
            task.status = STATUS_RETRYING
            task.retry_count += 1
            task.next_run_at = _now() + timedelta(seconds=_backoff_seconds(task.retry_count))
            task.error_code = code
            task.error_message = message
        else:
            task.status = STATUS_FAILED
            task.error_code = code
            task.error_message = message
            task.completed_at = _now()
        task.updated_at = _now()
        await db.commit()


async def cancel_task(task_id: str) -> bool:
    """取消任务：pending/retrying 直接置 cancelled；running 置取消标记（Worker 在候选题间中断）。"""
    async with get_db_session() as db:
        task = await db.get(ContentTask, task_id)
        if task is None:
            return False
        if task.status in (STATUS_PENDING, STATUS_RETRYING):
            task.status = STATUS_CANCELLED
            task.completed_at = _now()
            task.updated_at = _now()
            await db.commit()
            return True
        if task.status == STATUS_RUNNING:
            payload = dict(task.payload or {})
            payload["cancel_requested"] = True
            task.payload = payload
            task.updated_at = _now()
            await db.commit()
            return True
        return False


async def is_cancel_requested(task_id: str) -> bool:
    async with get_db_session() as db:
        task = await db.get(ContentTask, task_id)
        if task is None:
            return True
        if task.status == STATUS_CANCELLED:
            return True
        return bool((task.payload or {}).get("cancel_requested"))


# ── 序列化（API 响应）──
def serialize_task(task: ContentTask, *, ai_compat: bool = False) -> Dict[str, Any]:
    """通用任务序列化；ai_compat=True 时兼容旧 /ai-analysis/tasks/{id} 响应结构。"""
    progress = task.progress or {}
    base = {
        "task_id": task.id,
        "kind": task.kind,
        "ref_id": task.ref_id,
        "status": task.status,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "worker_id": task.worker_id,
        "progress": progress,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "heartbeat_at": task.heartbeat_at.isoformat() if task.heartbeat_at else None,
    }
    if not ai_compat:
        return base
    # 旧结构：status ∈ running/completed/failed/cancelled；analyzed/skipped/errors/result
    status_map = {
        STATUS_PENDING: "running",
        STATUS_RETRYING: "running",
        STATUS_RUNNING: "running",
        STATUS_SUCCEEDED: "completed",
        STATUS_PARTIAL: "completed",
        STATUS_FAILED: "failed",
        STATUS_CANCELLED: "cancelled",
    }
    return {
        "task_id": task.id,
        "batch_id": task.ref_id,
        "status": status_map.get(task.status, task.status),
        "total": progress.get("total", 0),
        "analyzed": progress.get("done", 0),
        "skipped": progress.get("skipped", 0),
        "errors": progress.get("errors", []),
        "result": progress.get("result"),
        "error": task.error_message,
    }
