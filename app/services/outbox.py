"""Durable SQL outbox and idempotent side-effect handlers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Memory, OutboxEvent, Question

logger = logging.getLogger(__name__)


async def enqueue_outbox(
    db,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    user_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    existing = await db.scalar(select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        user_id=user_id,
        payload=payload or {},
        idempotency_key=idempotency_key,
    )
    db.add(event)
    await db.flush()
    return event


def _question_embedding_text(question: Question) -> str:
    points = question.knowledge_points or []
    return "\n".join(
        part for part in (
            question.content,
            f"类别：{question.category}" if question.category else "",
            f"知识点：{'、'.join(points)}" if points else "",
            f"解析：{question.analysis}" if question.analysis else "",
        ) if part
    )


async def _handle_question_upsert(event: OutboxEvent) -> None:
    async with get_db_session() as db:
        question = await db.get(Question, event.aggregate_id)
        if question is None or question.review_status != "published":
            should_delete = True
            metadata, text = {}, ""
        else:
            should_delete = False
            metadata = {
                "content": question.content,
                "category": question.category,
                "difficulty": question.difficulty,
                "question_type": question.question_type,
                "course_id": question.course_id,
                "version_id": question.version_id,
                "review_status": question.review_status,
            }
            text = _question_embedding_text(question)
    if should_delete:
        await _handle_question_delete(event)
        return
    from app.services.vector_store import get_vector_store
    store = await get_vector_store()
    if not await store.add_question(event.aggregate_id, text, metadata):
        raise RuntimeError("question vector upsert failed")


async def _handle_question_delete(event: OutboxEvent) -> None:
    from app.services.vector_store import get_vector_store
    store = await get_vector_store()
    if not await store.delete_question(event.aggregate_id):
        # Qdrant deletes are idempotent; False here represents a transport failure.
        if not await store.check_availability():
            raise RuntimeError("question vector delete failed")


async def _handle_memory_upsert(event: OutboxEvent) -> None:
    async with get_db_session() as db:
        memory = await db.get(Memory, int(event.aggregate_id))
        if memory is None or memory.status != "active" or memory.deleted_at is not None:
            active_memory = None
        else:
            db.expunge(memory)
            active_memory = memory
    if active_memory is None:
        await _handle_memory_delete(event)
        return
    from app.services.memory_vector_store import get_memory_vector_store
    await get_memory_vector_store().upsert(active_memory)


async def _handle_memory_delete(event: OutboxEvent) -> None:
    from app.services.memory_vector_store import get_memory_vector_store
    await get_memory_vector_store().delete(int(event.aggregate_id))


async def _handle_learning_refresh(event: OutboxEvent) -> None:
    if not event.user_id:
        raise RuntimeError("learning refresh event is missing user_id")
    from app.services.profile_service import get_profile_service
    from app.services.skill_aggregator import SkillAggregator

    await SkillAggregator().recalculate_skills(event.user_id)
    ok = await get_profile_service().incremental_update(
        event.user_id, category=str((event.payload or {}).get("category") or "")
    )
    if not ok:
        raise RuntimeError("profile refresh failed")


async def _handle_review_complete(event: OutboxEvent) -> None:
    from app.services.learning_hub import complete_review
    payload = event.payload or {}
    await complete_review(
        event.user_id,
        int(payload["review_schedule_id"]),
        attempt_id=payload.get("attempt_id"),
        idempotency_key=event.idempotency_key,
    )


_HANDLERS = {
    "question.vector.upsert": _handle_question_upsert,
    "question.vector.delete": _handle_question_delete,
    "memory.vector.upsert": _handle_memory_upsert,
    "memory.vector.delete": _handle_memory_delete,
    "learning.refresh": _handle_learning_refresh,
    "review.complete": _handle_review_complete,
}


async def process_outbox_event(event_id: str) -> bool:
    async with get_db_session() as db:
        event = await db.get(OutboxEvent, event_id)
        if event is None or event.status == "completed":
            return True
        event_type = event.event_type
    handler = _HANDLERS.get(event_type)
    if handler is None:
        error: Exception = RuntimeError(f"unsupported outbox event: {event_type}")
    else:
        try:
            await handler(event)
            async with get_db_session() as db:
                row = await db.get(OutboxEvent, event_id)
                row.status = "completed"
                row.completed_at = datetime.now(timezone.utc)
                row.locked_at = None
                row.last_error = None
            return True
        except Exception as exc:  # side effects are retried by design
            error = exc

    async with get_db_session() as db:
        row = await db.get(OutboxEvent, event_id)
        row.attempts = int(row.attempts or 0) + 1
        row.last_error = str(error)[:4000]
        row.locked_at = None
        if row.attempts >= settings.OUTBOX_MAX_RETRIES:
            row.status = "dead"
        else:
            row.status = "pending"
            delay = min(900, 5 * (2 ** max(0, row.attempts - 1)))
            row.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    logger.warning("Outbox 事件处理失败: id=%s error=%s", event_id, error)
    return False


async def process_outbox_batch() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    stale = now - timedelta(minutes=10)
    claimed: list[str] = []
    async with get_db_session() as db:
        stmt = (
            select(OutboxEvent)
            .where(
                or_(
                    (OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now),
                    (OutboxEvent.status == "processing") & (OutboxEvent.locked_at < stale),
                )
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
            .limit(settings.OUTBOX_BATCH_SIZE)
        )
        bind = db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        rows = list((await db.execute(stmt)).scalars())
        for row in rows:
            row.status = "processing"
            row.locked_at = now
            claimed.append(row.id)
    results = await asyncio.gather(*(process_outbox_event(event_id) for event_id in claimed))
    return {"claimed": len(claimed), "completed": sum(bool(value) for value in results)}


async def outbox_health() -> dict[str, Any]:
    try:
        now = datetime.now(timezone.utc)
        async with get_db_session() as db:
            counts = dict((await db.execute(
                select(OutboxEvent.status, func.count(OutboxEvent.id)).group_by(OutboxEvent.status)
            )).all())
            oldest = await db.scalar(select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "pending"))
        age = max(0, int((now - oldest).total_seconds())) if oldest else 0
        healthy = int(counts.get("dead", 0)) == 0 and age <= 60
        return {
            "status": "healthy" if healthy else "degraded",
            "pending": int(counts.get("pending", 0)),
            "processing": int(counts.get("processing", 0)),
            "dead": int(counts.get("dead", 0)),
            "oldest_pending_seconds": age,
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}


def dispatch_outbox_best_effort(event_id: str) -> None:
    # SQLite's single-connection test/development mode cannot safely interleave
    # a background transaction with the request transaction. The durable poller
    # remains the delivery mechanism there.
    from app.data import database
    factory = database.async_session_factory
    bind = factory.kw.get("bind") if factory is not None else None
    if bind is not None and bind.dialect.name == "sqlite":
        return
    task = asyncio.create_task(process_outbox_event(event_id))
    task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
