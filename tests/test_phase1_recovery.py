from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, OutboxEvent


@pytest.mark.asyncio
async def test_database_init_close_and_reinitialize(monkeypatch):
    import app.data.database as database

    await database.close_db()
    monkeypatch.setattr(database, "_get_database_url", lambda: "sqlite+aiosqlite:///:memory:")

    async def no_migration(_url):
        return None

    monkeypatch.setattr(database, "_run_alembic_migration", no_migration)
    await database.init_db()
    assert database.DB_AVAILABLE is True
    assert database.engine is not None
    assert database.async_session_factory is not None

    await database.close_db()
    assert database.DB_AVAILABLE is False
    assert database.engine is None
    assert database.async_session_factory is None

    await database.init_db()
    assert database.DB_AVAILABLE is True
    assert database.async_session_factory is not None
    await database.close_db()


@pytest.mark.asyncio
async def test_database_failed_probe_can_recover(monkeypatch):
    import app.data.database as database

    class BrokenConnection:
        async def __aenter__(self):
            raise ConnectionError("database refused")

        async def __aexit__(self, *_args):
            return False

    class BrokenEngine:
        def connect(self):
            return BrokenConnection()

        async def dispose(self):
            return None

    real_create = database.create_async_engine
    monkeypatch.setattr(database, "create_async_engine", lambda *_args, **_kwargs: BrokenEngine())
    monkeypatch.setattr(database, "_get_database_url", lambda: "postgresql+asyncpg://invalid/test")
    await database.init_db()
    assert database.DB_AVAILABLE is False
    assert database.engine is None
    assert database.async_session_factory is None

    monkeypatch.setattr(database, "create_async_engine", real_create)
    monkeypatch.setattr(database, "_get_database_url", lambda: "sqlite+aiosqlite:///:memory:")

    async def no_migration(_url):
        return None

    monkeypatch.setattr(database, "_run_alembic_migration", no_migration)
    await database.init_db()
    assert database.DB_AVAILABLE is True
    await database.close_db()


@pytest.mark.asyncio
async def test_dead_event_recovery_is_dry_run_by_default_and_preserves_evidence(monkeypatch):
    import app.data.database as database
    from app.services.outbox import outbox_health, recover_dead_events

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        supported = OutboxEvent(
            event_type="question.vector.upsert", aggregate_type="question", aggregate_id="q1",
            idempotency_key="recover-q1", status="dead", attempts=8, last_error="qdrant unavailable",
        )
        unsupported = OutboxEvent(
            event_type="unknown.side.effect", aggregate_type="test", aggregate_id="x",
            idempotency_key="recover-unknown", status="dead", attempts=8, last_error="unsupported",
        )
        db.add_all([supported, unsupported])
        await db.commit()
        supported_id = supported.id
        unsupported_id = unsupported.id

    dry_run = await recover_dead_events(apply=False, execution_id="audit-dry-run")
    assert [row["id"] for row in dry_run["recoverable"]] == [supported_id]
    assert dry_run["skipped"] == [{
        "id": unsupported_id, "event_type": "unknown.side.effect", "reason": "unsupported_event_type"
    }]
    async with factory() as db:
        assert (await db.get(OutboxEvent, supported_id)).status == "dead"

    applied = await recover_dead_events(apply=True, execution_id="audit-apply")
    assert applied["requeued"] == 1
    health = await outbox_health()
    assert health["pending"] == 1
    assert health["processing"] == 0
    assert health["completed"] == 0
    assert health["dead"] == 1
    assert health["failures_by_event_type"] == {
        "question.vector.upsert": 1,
        "unknown.side.effect": 1,
    }
    async with factory() as db:
        row = await db.get(OutboxEvent, supported_id)
        assert row.status == "pending"
        assert row.attempts == 8
        assert row.last_error == "qdrant unavailable"
        assert row.payload["_recovery_audit"][-1]["execution_id"] == "audit-apply"
        assert (await db.get(OutboxEvent, unsupported_id)).status == "dead"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collections", "actual_size", "expected_code"),
    [([], None, "collection_missing"), (["questions"], 384, "vector_dimension_mismatch")],
)
async def test_vector_health_distinguishes_collection_and_dimension(
    monkeypatch, collections, actual_size, expected_code
):
    import qdrant_client
    import app.services.dependency_health as health

    class Client:
        def __init__(self, **_kwargs):
            pass

        def get_collections(self):
            return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in collections])

        def get_collection(self, _name):
            vectors = SimpleNamespace(size=actual_size)
            return SimpleNamespace(
                config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)), points_count=2
            )

    monkeypatch.setattr(qdrant_client, "QdrantClient", Client)
    monkeypatch.setattr(health.settings, "QUESTION_QDRANT_COLLECTION", "questions")
    monkeypatch.setattr(health.settings, "VECTOR_SIZE", 512)
    monkeypatch.setattr(
        health, "get_embedding_service", lambda: SimpleNamespace(health=lambda: {"status": "healthy"})
    )
    result = await health.vector_dependency_health()
    assert result["code"] == expected_code
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_vector_health_reports_embedding_unavailable(monkeypatch):
    import app.services.dependency_health as health

    monkeypatch.setattr(
        health,
        "get_embedding_service",
        lambda: SimpleNamespace(health=lambda: {"status": "degraded", "error": "model missing"}),
    )
    result = await health.vector_dependency_health()
    assert result["code"] == "embedding_unavailable"
