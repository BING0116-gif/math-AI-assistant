"""Durable SQL outbox and idempotent side-effect handlers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select, update

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import EventIdempotency, KnowledgePoint, KnowledgePointResource, LearningRecord, Memory, OutboxEvent, Question

logger = logging.getLogger(__name__)


def _utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite's naive timestamp reads to UTC-aware values."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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


async def enqueue_learning_record(
    *, user_id: str, event_data: dict[str, Any], event_id: str | None,
    session_factory=None,
) -> bool:
    """Persist a chat/behavior fact as a durable outbox event.

    The request commits the outbox row before returning. A scheduler retries
    the actual LearningRecord insert after crashes or database outages, so
    behavior signals cannot disappear with an in-memory queue.
    """
    if not user_id:
        return False
    import uuid
    factory = session_factory or get_db_session
    stable_id = str(event_id or uuid.uuid4().hex)
    payload = dict(event_data)
    payload["user_id"] = user_id
    payload["event_id"] = stable_id
    key = f"learning-record:{user_id}:{stable_id}"
    async with factory() as db:
        await enqueue_outbox(
            db, event_type="learning.record", aggregate_type="learning_record",
            aggregate_id=stable_id, user_id=user_id,
            payload=payload, idempotency_key=key,
        )
        await db.commit()
    return True


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
                "content_kind": "question",
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


async def _handle_learning_record(event: OutboxEvent) -> None:
    """Materialize one durable behavior event into LearningRecord idempotently."""
    payload = dict(event.payload or {})
    user_id = event.user_id or str(payload.get("user_id") or "")
    event_id = str(payload.get("event_id") or event.aggregate_id)
    if not user_id:
        raise RuntimeError("learning record event is missing user_id")
    allowed = {
        "user_id", "question_id", "event_type", "question_content", "category",
        "sub_categories", "difficulty", "user_answer", "correct_answer", "is_correct",
        "time_spent", "hint_count", "tools_used", "error_category", "error_reason",
        "correction_suggestion", "metadata_", "created_at",
    }
    values = {key: value for key, value in payload.items() if key in allowed}
    values["user_id"] = user_id
    values["question_content"] = str(values.get("question_content") or "")
    values["category"] = str(values.get("category") or "未分类")
    if isinstance(values.get("sub_categories"), list):
        values["sub_categories"] = ",".join(str(item) for item in values["sub_categories"])
    if isinstance(values.get("tools_used"), list):
        values["tools_used"] = ",".join(str(item) for item in values["tools_used"])
    if values.get("time_spent") is not None:
        values["time_spent"] = int(float(values["time_spent"]))
    if isinstance(values.get("created_at"), str):
        values["created_at"] = datetime.fromisoformat(values["created_at"].replace("Z", "+00:00"))
    if values.get("is_correct") == "":
        values["is_correct"] = None
    async with get_db_session() as db:
        async with db.begin():
            existing = await db.scalar(select(EventIdempotency).where(EventIdempotency.event_id == event_id))
            if existing is not None:
                return
            db.add(EventIdempotency(
                event_id=event_id, event_type=str(values.get("event_type") or "learning_record")[:64],
                processed_at=int(datetime.now(timezone.utc).timestamp()), status="processed",
            ))
            db.add(LearningRecord(**values))


async def _handle_review_complete(event: OutboxEvent) -> None:
    from app.services.learning_hub import complete_review
    payload = event.payload or {}
    await complete_review(
        event.user_id,
        int(payload["review_schedule_id"]),
        attempt_id=payload.get("attempt_id"),
        idempotency_key=event.idempotency_key,
    )


async def _handle_chat_context_checkpoint(event: OutboxEvent) -> None:
    from app.services.chat_context_checkpoint import generate_checkpoint
    await generate_checkpoint(event.user_id, event.aggregate_id, int(event.payload["target_message_id"]))


_HANDLERS = {
    "chat.context.checkpoint": _handle_chat_context_checkpoint,
    "question.vector.upsert": _handle_question_upsert,
    "question.vector.delete": _handle_question_delete,
    "knowledge_resource.vector.upsert": _handle_knowledge_resource_upsert,
    "memory.vector.upsert": _handle_memory_upsert,
    "memory.vector.delete": _handle_memory_delete,
    "learning.refresh": _handle_learning_refresh,
    "learning.record": _handle_learning_record,
    "review.complete": _handle_review_complete,
}


async def process_outbox_event(event_id: str) -> bool:
    worker_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(minutes=10)
    async with get_db_session() as db:
        event = await db.get(OutboxEvent, event_id)
        if event is None or event.status == "completed":
            return True
        if event.status == "processing" and _utc(event.lease_until) and _utc(event.lease_until) > now:
            return False
        event.status = "processing"
        event.locked_at = now
        event.lease_until = lease_until
        event.locked_by = worker_id
        event_type = event.event_type
    handler = _HANDLERS.get(event_type)
    if handler is None:
        error: Exception = RuntimeError(f"unsupported outbox event: {event_type}")
    else:
        try:
            await handler(event)
            async with get_db_session() as db:
                row = await db.get(OutboxEvent, event_id)
                if row is None or row.locked_by != worker_id:
                    return False
                row.status = "completed"
                row.completed_at = datetime.now(timezone.utc)
                row.locked_at = None
                row.lease_until = None
                row.locked_by = None
                row.last_error = None
            return True
        except Exception as exc:  # side effects are retried by design
            error = exc

    async with get_db_session() as db:
        row = await db.get(OutboxEvent, event_id)
        if row is None or row.locked_by != worker_id:
            return False
        row.attempts = int(row.attempts or 0) + 1
        row.last_error = str(error)[:4000]
        row.locked_at = None
        row.lease_until = None
        row.locked_by = None
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
    stale = now
    worker_id = uuid.uuid4().hex
    lease_until = now + timedelta(minutes=10)
    claimed: list[str] = []
    async with get_db_session() as db:
        stmt = (
            select(OutboxEvent)
            .where(
                or_(
                    (OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now),
                    (OutboxEvent.status == "processing") & or_(
                        OutboxEvent.lease_until <= stale,
                        (OutboxEvent.lease_until.is_(None)) & (OutboxEvent.locked_at < now - timedelta(minutes=10)),
                    ),
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
            claim_filter = or_(
                (OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now),
                (OutboxEvent.status == "processing") & or_(
                    OutboxEvent.lease_until <= now,
                    (OutboxEvent.lease_until.is_(None)) & (OutboxEvent.locked_at < now - timedelta(minutes=10)),
                ),
            )
            result = await db.execute(
                update(OutboxEvent).where(OutboxEvent.id == row.id, claim_filter).values(
                    status="processing", locked_at=now, lease_until=lease_until, locked_by=worker_id
                ).execution_options(synchronize_session=False)
            )
            if result.rowcount == 1:
                claimed.append(row.id)
    results = await asyncio.gather(*(_process_claimed_event(event_id, worker_id) for event_id in claimed))
    return {"claimed": len(claimed), "completed": sum(bool(value) for value in results)}


async def _process_claimed_event(event_id: str, worker_id: str) -> bool:
    """Run a batch claim without re-claiming it under another token."""
    async with get_db_session() as db:
        event = await db.get(OutboxEvent, event_id)
        if event is None or event.status != "processing" or event.locked_by != worker_id:
            return False
        event_type = event.event_type
    handler = _HANDLERS.get(event_type)
    error = None
    try:
        if handler is None:
            raise RuntimeError(f"unsupported outbox event: {event_type}")
        await handler(event)
    except Exception as exc:
        error = exc
    async with get_db_session() as db:
        row = await db.get(OutboxEvent, event_id)
        if row is None or row.locked_by != worker_id:
            return False
        if error is None:
            row.status = "completed"; row.completed_at = datetime.now(timezone.utc); row.last_error = None
        else:
            row.attempts = int(row.attempts or 0) + 1; row.last_error = str(error)[:4000]
            if row.attempts >= settings.OUTBOX_MAX_RETRIES:
                row.status = "dead"
            else:
                row.status = "pending"; row.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(900, 5 * (2 ** max(0, row.attempts - 1))))
        row.locked_at = None; row.lease_until = None; row.locked_by = None
    if error:
        logger.warning("Outbox 事件处理失败: id=%s error=%s", event_id, error)
    return error is None


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
