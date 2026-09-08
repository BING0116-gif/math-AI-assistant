"""Owner-scoped active learning session tracking."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.data.database import get_db_session
from app.data.models import LearningActivitySession

MAX_HEARTBEAT_SECONDS = 300
ALLOWED_CONTEXTS = {"chat", "knowledge", "practice", "assessment", "exam"}


class ActivityError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def payload(row: LearningActivitySession) -> dict:
    return {
        "id": row.id, "client_session_id": row.client_session_id,
        "context_type": row.context_type, "context_id": row.context_id,
        "started_at": row.started_at, "last_heartbeat_at": row.last_heartbeat_at,
        "ended_at": row.ended_at, "active_seconds": row.active_seconds,
        "status": row.status,
    }


async def start_activity(user_id: str, client_session_id: str, context_type: str, context_id: str | None) -> dict:
    if context_type not in ALLOWED_CONTEXTS:
        raise ActivityError("INVALID_CONTEXT", "不支持的学习场景")
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        row = await db.scalar(select(LearningActivitySession).where(
            LearningActivitySession.user_id == user_id,
            LearningActivitySession.client_session_id == client_session_id,
        ))
        if row is None:
            row = LearningActivitySession(
                user_id=user_id, client_session_id=client_session_id,
                context_type=context_type, context_id=context_id,
                started_at=now, last_heartbeat_at=now,
            )
            db.add(row)
            await db.flush()
        elif row.context_type != context_type or row.context_id != context_id:
            raise ActivityError("IDEMPOTENCY_CONFLICT", "活动会话标识已用于其他学习场景")
        return payload(row)


async def heartbeat_activity(user_id: str, activity_id: str, client_time: datetime | None = None) -> dict:
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        row = await db.scalar(select(LearningActivitySession).where(
            LearningActivitySession.id == activity_id,
            LearningActivitySession.user_id == user_id,
        ).with_for_update())
        if row is None:
            raise ActivityError("NOT_FOUND", "学习活动不存在")
        if row.status != "active":
            return payload(row)
        last = _utc(row.last_heartbeat_at)
        elapsed = max(0, int((now - last).total_seconds()))
        # Duplicate/rapid heartbeats add no time; long gaps are treated as inactivity.
        if 5 <= elapsed <= MAX_HEARTBEAT_SECONDS:
            row.active_seconds += elapsed
        elif elapsed > MAX_HEARTBEAT_SECONDS:
            row.status, row.ended_at = "timed_out", last
            return payload(row)
        row.last_heartbeat_at = now
        return payload(row)


async def end_activity(user_id: str, activity_id: str) -> dict:
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        row = await db.scalar(select(LearningActivitySession).where(
            LearningActivitySession.id == activity_id,
            LearningActivitySession.user_id == user_id,
        ).with_for_update())
        if row is None:
            raise ActivityError("NOT_FOUND", "学习活动不存在")
        if row.status == "active":
            elapsed = max(0, int((now - _utc(row.last_heartbeat_at)).total_seconds()))
            if 5 <= elapsed <= MAX_HEARTBEAT_SECONDS:
                row.active_seconds += elapsed
            row.status, row.ended_at = "ended", now
        return payload(row)
