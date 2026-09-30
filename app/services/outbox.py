"""Durable SQL outbox and idempotent side-effect handlers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import KnowledgePoint, KnowledgePointResource, Memory, OutboxEvent, Question

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


async def _handle_knowledge_resource_upsert(event: OutboxEvent) -> None:
    """Project a reviewed learning resource into the rebuildable vector index."""
    async with get_db_session() as db:
        resource = await db.get(KnowledgePointResource, event.aggregate_id)
        if resource is None or resource.status != "published":
            should_delete = True
            text, metadata = "", {}
        else:
            point = await db.get(KnowledgePoint, resource.knowledge_point_id)
            if point is None:
                should_delete = True
                text, metadata = "", {}
            else:
                should_delete = False
                text = "\n".join((point.name, resource.title, resource.body))
                metadata = {
                    "content_kind": "knowledge_resource",
                    "resource_id": resource.id,
                    "resource_type": resource.resource_type,
                    "knowledge_point_id": point.id,
                    "knowledge_point_code": point.code,
                    "course_id": point.course_id,
                    "version_id": point.version_id,
                    "review_status": resource.status,
                    "content_hash": resource.content_hash,
                }
    from app.services.vector_store import get_vector_store
    store = await get_vector_store()
    vector_id = f"knowledge-resource:{event.aggregate_id}"
    if should_delete:
        if not await store.delete_question(vector_id) and not await store.check_availability():
            raise RuntimeError("knowledge resource vector delete failed")
        return
    if not await store.add_question(vector_id, text, metadata):
        raise RuntimeError("knowledge resource vector upsert failed")


async def _handle_memory_upsert(event: OutboxEvent) -> None:
    async with get_db_session() as db:
        memory = await db.get(Memory, int(event.aggregate_id))
        if memory is None or memory.status != "active" or memory.deleted_at is not None:
            active_memory = None
            tags = []
        else:
            from sqlalchemy import select
            from app.data.models import MemoryTag

            tags = list((await db.execute(
                select(MemoryTag.tag_name).where(MemoryTag.memory_id == memory.id)
            )).scalars())
            db.expunge(memory)
            active_memory = memory
    if active_memory is None:
        await _handle_memory_delete(event)
        return
    from app.services.memory_vector_store import get_memory_vector_store
    await get_memory_vector_store().upsert(active_memory, tags=tags)


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
    "knowledge_resource.vector.upsert": _handle_knowledge_resource_upsert,
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
            failures = dict((await db.execute(
                select(OutboxEvent.event_type, func.count(OutboxEvent.id))
                .where(OutboxEvent.last_error.is_not(None))
                .group_by(OutboxEvent.event_type)
            )).all())
        if oldest and oldest.tzinfo is None:
            # SQLite drops timezone metadata; PostgreSQL keeps it. Treat stored
            # outbox timestamps as UTC in both backends.
            oldest = oldest.replace(tzinfo=timezone.utc)
        age = max(0, int((now - oldest).total_seconds())) if oldest else 0
        healthy = int(counts.get("dead", 0)) == 0 and age <= 60
        normalized_counts = {
            status: int(counts.get(status, 0))
            for status in ("pending", "processing", "completed", "dead")
        }
        from app.observability import OUTBOX_EVENTS, OUTBOX_FAILURES, OUTBOX_OLDEST_PENDING

        for status, count in normalized_counts.items():
            OUTBOX_EVENTS.labels(status).set(count)
        OUTBOX_OLDEST_PENDING.set(age)
        known_types = set(_HANDLERS)
        for event_type in known_types | {"other"}:
            count = sum(value for key, value in failures.items() if key not in known_types) if event_type == "other" else failures.get(event_type, 0)
            OUTBOX_FAILURES.labels(event_type).set(int(count))
        return {
            "status": "healthy" if healthy else "degraded",
            **normalized_counts,
            "oldest_pending_seconds": age,
            "failures_by_event_type": {str(key): int(value) for key, value in failures.items()},
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}


async def recover_dead_events(
    *, event_id: str | None = None, apply: bool = False, execution_id: str
) -> dict[str, Any]:
    """Audit or requeue supported dead events while preserving failure evidence."""
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        query = select(OutboxEvent).where(OutboxEvent.status == "dead")
        if event_id:
            query = query.where(OutboxEvent.id == event_id)
        rows = list((await db.execute(query.order_by(OutboxEvent.created_at))).scalars())
        recoverable = [row for row in rows if row.event_type in _HANDLERS]
        skipped = [
            {"id": row.id, "event_type": row.event_type, "reason": "unsupported_event_type"}
            for row in rows if row.event_type not in _HANDLERS
        ]
        snapshots = [
            {
                "id": row.id,
                "event_type": row.event_type,
                "attempts": int(row.attempts or 0),
                "last_error": row.last_error,
            }
            for row in recoverable
        ]
        if apply:
            for row in recoverable:
                payload = dict(row.payload or {})
                audit = list(payload.get("_recovery_audit") or [])
                audit.append({
                    "execution_id": execution_id,
                    "requeued_at": now.isoformat(),
                    "attempts": int(row.attempts or 0),
                    "last_error": row.last_error,
                })
                payload["_recovery_audit"] = audit[-20:]
                row.payload = payload
                row.status = "pending"
                row.available_at = now
                row.locked_at = None
    return {
        "recoverable": snapshots,
        "skipped": skipped,
        "requeued": len(recoverable) if apply else 0,
    }


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
