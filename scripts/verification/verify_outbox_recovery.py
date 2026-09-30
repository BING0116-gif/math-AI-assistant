"""Disposable PostgreSQL/Qdrant fault-recovery acceptance for Phase 1.

The caller must provide an isolated PostgreSQL database and a disposable Qdrant
collection whose name starts with ``phase1_``. No repository data is read or
changed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select

from app.config.settings import settings
from app.data.database import close_db, get_db_session, init_db
from app.data.models import OutboxEvent, Question


class _Vector(list):
    def tolist(self):
        return list(self)


class _DeterministicEmbedding:
    def get_embedding_dimension(self):
        return settings.VECTOR_SIZE

    def encode(self, _text, normalize_embeddings=True):
        return _Vector([0.0] * settings.VECTOR_SIZE)


async def main() -> None:
    database_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL
    if not database_url.startswith("postgresql"):
        raise SystemExit("Disposable PostgreSQL is required")
    if not settings.QUESTION_QDRANT_COLLECTION.startswith("phase1_"):
        raise SystemExit("QUESTION_QDRANT_COLLECTION must start with phase1_")

    from app.services import embedding_service, vector_store
    from app.services.dependency_health import vector_dependency_health
    from app.services.outbox import enqueue_outbox, process_outbox_event, recover_dead_events

    embedding = embedding_service.get_embedding_service()
    embedding._model = _DeterministicEmbedding()
    embedding._error = None

    await init_db()
    try:
        event_id = ""
        async with get_db_session() as db:
            question = Question(
                id="phase1-recovery-q1",
                content="求极限 lim(x→0) sin(x)/x。",
                question_type="short_answer",
                answer="1",
                category="极限",
                difficulty=2,
                review_status="published",
            )
            db.add(question)
            await db.flush()
            event = await enqueue_outbox(
                db,
                event_type="question.vector.upsert",
                aggregate_type="question",
                aggregate_id=question.id,
                idempotency_key="phase1-recovery-q1:v1",
            )
            event_id = event.id

        original_retries = settings.OUTBOX_MAX_RETRIES
        settings.OUTBOX_MAX_RETRIES = 1
        vector_store._qdrant_vector_store_instance = vector_store.QdrantVectorStoreManager(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT + 1,
            collection_name=settings.QUESTION_QDRANT_COLLECTION,
            vector_size=settings.VECTOR_SIZE,
            max_retries=1,
            retry_delay=0,
            availability_check_interval=0,
        )
        assert await process_outbox_event(event_id) is False
        settings.OUTBOX_MAX_RETRIES = original_retries

        async with get_db_session() as db:
            failed = await db.get(OutboxEvent, event_id)
            assert failed.status == "dead" and failed.attempts == 1 and failed.last_error

        before = await vector_dependency_health()
        assert before["code"] == "collection_missing", before

        good_store = vector_store.QdrantVectorStoreManager(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            collection_name=settings.QUESTION_QDRANT_COLLECTION,
            vector_size=settings.VECTOR_SIZE,
            max_retries=1,
            retry_delay=0,
            availability_check_interval=0,
        )
        vector_store._qdrant_vector_store_instance = good_store
        await good_store.initialize()

        recovery = await recover_dead_events(
            event_id=event_id, apply=True, execution_id="phase1-disposable-acceptance"
        )
        assert recovery["requeued"] == 1
        assert await process_outbox_event(event_id) is True
        assert await process_outbox_event(event_id) is True

        stats = await good_store.get_collection_stats()
        ids = await good_store.get_all_ids()
        async with get_db_session() as db:
            completed = int(await db.scalar(select(func.count(OutboxEvent.id)).where(
                OutboxEvent.status == "completed"
            )) or 0)
            dead = int(await db.scalar(select(func.count(OutboxEvent.id)).where(
                OutboxEvent.status == "dead"
            )) or 0)
        assert stats["total_documents"] == 1
        assert ids == ["phase1-recovery-q1"]
        assert completed == 1 and dead == 0
        print(json.dumps({
            "fault": "qdrant_network_unreachable",
            "diagnostic_after_restore": before["code"],
            "requeued": recovery["requeued"],
            "completed": completed,
            "dead": dead,
            "sql_published": 1,
            "qdrant_points": stats["total_documents"],
            "difference": 0,
            "idempotent_replay": True,
        }, ensure_ascii=False))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
