"""Canonical lifecycle and persistence helpers for asynchronous work."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Final
from uuid import uuid4
from sqlalchemy import select
from app.data.database import get_db_session
from app.data.models import AsyncTask

PENDING: Final = "pending"
RUNNING: Final = "running"
SUCCEEDED: Final = "succeeded"
RETRYABLE_FAILED: Final = "retryable_failed"
PERMANENTLY_FAILED: Final = "permanently_failed"
CANCELLED: Final = "cancelled"
STATUSES: Final = frozenset({PENDING, RUNNING, SUCCEEDED, RETRYABLE_FAILED, PERMANENTLY_FAILED, CANCELLED})
TRANSITIONS: Final = {PENDING: frozenset({RUNNING, CANCELLED}), RUNNING: frozenset({SUCCEEDED, RETRYABLE_FAILED, PERMANENTLY_FAILED, CANCELLED}), RETRYABLE_FAILED: frozenset({PENDING, RUNNING, CANCELLED}), SUCCEEDED: frozenset(), PERMANENTLY_FAILED: frozenset(), CANCELLED: frozenset()}

class InvalidTaskTransition(ValueError):
    pass

def validate_transition(current: str, target: str) -> None:
    if current not in STATUSES or target not in STATUSES or target not in TRANSITIONS[current]:
        raise InvalidTaskTransition(f"illegal task transition: {current!r} -> {target!r}")

def legacy_status(status: str, *, attempts: int = 0, max_attempts: int | None = None) -> str:
    if status in {"pending", "queued", "created"}: return PENDING
    if status in {"retrying"}: return RETRYABLE_FAILED
    if status in {"running", "processing", "analyzing", "validating", "verifying"}: return RUNNING
    if status in {"succeeded", "completed", "partially_succeeded", "fallback", "pass"}: return SUCCEEDED
    if status in {"cancelled", "canceled", "abandoned"}: return CANCELLED
    if status in {"failed", "error", "dead", "doubtful"}: return RETRYABLE_FAILED if max_attempts is None or attempts < max_attempts else PERMANENTLY_FAILED
    return PENDING

def transition(task: AsyncTask, target: str, *, error: str | None = None) -> AsyncTask:
    validate_transition(task.status, target)
    now = datetime.now(timezone.utc)
    task.status = target; task.updated_at = now
    if target == RUNNING:
        task.attempts += 1; task.started_at = task.started_at or now
    elif target == SUCCEEDED: task.succeeded_at = now; task.lease_until = None
    elif target in {RETRYABLE_FAILED, PERMANENTLY_FAILED}: task.failed_at = now; task.last_error = error; task.lease_until = None
    elif target == CANCELLED: task.cancelled_at = now; task.lease_until = None
    return task

async def create_task(*, task_type: str, resource_type: str, resource_id: str, user_id: str | None = None, idempotency_key: str | None = None, payload: dict | None = None, max_attempts: int | None = None) -> AsyncTask:
    async with get_db_session() as db:
        existing = None
        if idempotency_key:
            query = select(AsyncTask).where(AsyncTask.task_type == task_type, AsyncTask.idempotency_key == idempotency_key)
            if user_id is not None: query = query.where(AsyncTask.user_id == user_id)
            existing = (await db.execute(query)).scalar_one_or_none()
        if existing: return existing
        task = AsyncTask(id=str(uuid4()), task_type=task_type, resource_type=resource_type, resource_id=resource_id, user_id=user_id, idempotency_key=idempotency_key, payload=payload, max_attempts=max_attempts)
        db.add(task); await db.commit(); await db.refresh(task); return task
