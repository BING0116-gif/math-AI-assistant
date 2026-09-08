from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, OutboxEvent, User
from app.lifespan import validate_runtime_security
from app.services.safe_math import SafeExpressionError, expressions_equivalent, parse_safe_expression


@pytest.mark.parametrize(
    ("student", "canonical", "variables"),
    [
        ("2*(x+1)", "2*x+2", ["x"]),
        ("x^2+1", "x*x+1", ["x"]),
        ("2*L", "L+L", ["L"]),
        ("sin(x)^2+cos(x)^2", "1", ["x"]),
    ],
)
def test_safe_expression_accepts_supported_equivalence(student, canonical, variables):
    assert expressions_equivalent(student, canonical, variables)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "x.__class__",
        "open('secret')",
        "[x for x in range(10)]",
        "x[0]",
        "y+1",
        "x^1000",
    ],
)
def test_safe_expression_rejects_code_and_unapproved_variables(expression):
    with pytest.raises(SafeExpressionError):
        parse_safe_expression(expression, ["x"])


def test_safe_expression_rejects_excessive_length_and_depth():
    with pytest.raises(SafeExpressionError):
        parse_safe_expression("1" * 257, [])
    with pytest.raises(SafeExpressionError):
        parse_safe_expression("-" * 20 + "x", ["x"])


def test_jwt_runtime_validation_fails_closed(monkeypatch):
    from app.lifespan import settings
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_runtime_security()
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "x" * 32)
    validate_runtime_security()
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "short")
    validate_runtime_security()


def test_cache_manager_uses_configured_redis_url(monkeypatch):
    import app.services.cache as cache_module
    from app.config.settings import settings

    monkeypatch.setattr(cache_module, "_cache_manager", None)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://configured-redis:6379/7")

    assert cache_module.get_cache_manager().redis_url == "redis://configured-redis:6379/7"


@pytest.mark.asyncio
async def test_outbox_failure_is_retried_without_losing_sql_fact(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="outbox-user", username="outbox", email="outbox@example.test", password_hash="x"))
        await db.commit()
    from app.services.outbox import enqueue_outbox, process_outbox_event
    async with database.get_db_session() as db:
        row = await enqueue_outbox(
            db, event_type="learning.refresh", aggregate_type="test", aggregate_id="1",
            user_id="outbox-user", idempotency_key="outbox-test-1",
        )
        event_id = row.id
    monkeypatch.setattr("app.services.skill_aggregator.SkillAggregator.recalculate_skills", AsyncMock(side_effect=RuntimeError("boom")))
    assert await process_outbox_event(event_id) is False
    async with factory() as db:
        row = await db.get(OutboxEvent, event_id)
        assert row.status == "pending" and row.attempts == 1 and "boom" in row.last_error
        assert await db.get(User, "outbox-user") is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_processing_outbox_event_is_reclaimed_once(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    import app.services.outbox as outbox_module

    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="reclaim-user", username="reclaim", email="reclaim@example.test", password_hash="x"))
        await db.commit()

    async with database.get_db_session() as db:
        row = await outbox_module.enqueue_outbox(
            db,
            event_type="learning.refresh",
            aggregate_type="test",
            aggregate_id="reclaim-1",
            user_id="reclaim-user",
            idempotency_key="outbox-stale-reclaim-1",
        )
        event_id = row.id
        row.status = "processing"
        row.locked_at = datetime.now(timezone.utc) - timedelta(minutes=11)

    handler = AsyncMock()
    monkeypatch.setitem(outbox_module._HANDLERS, "learning.refresh", handler)

    assert await outbox_module.process_outbox_batch() == {"claimed": 1, "completed": 1}
    handler.assert_awaited_once()
    async with factory() as db:
        row = await db.get(OutboxEvent, event_id)
        assert row.status == "completed"
        assert row.completed_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_embedding_service_never_generates_fallback_vectors(monkeypatch):
    from app.services.embedding_service import EmbeddingService
    service = EmbeddingService()
    with pytest.raises(RuntimeError, match="not ready"):
        service.encode("极限与连续")
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 512
    model.encode.return_value.tolist.return_value = [0.1] * 512
    service._model = model
    assert len(service.encode("极限与连续")) == 512


@pytest.mark.asyncio
async def test_memory_sql_fact_and_vector_events_share_transaction(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="memory-user", username="memory", email="memory@example.test", password_hash="x"))
        await db.commit()
    from app.data.models import Memory
    from app.services.memory_store import MemoryStore
    store = MemoryStore()
    memory_id = await store.create_error_memory(
        user_id="memory-user", question_id="question-1", question_content="求函数极限", user_answer="0",
        correct_answer="1", error_type="calculation", high_category="高等数学",
        category="极限",
    )
    assert memory_id is not None
    async with factory() as db:
        memory = await db.get(Memory, memory_id)
        event = await db.scalar(select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "memory", OutboxEvent.aggregate_id == str(memory_id)
        ))
        assert memory.status == "active"
        assert event.event_type == "memory.vector.upsert" and event.status == "pending"
    assert await store.archive_memory(memory_id)
    async with factory() as db:
        events = list((await db.execute(select(OutboxEvent).where(
            OutboxEvent.aggregate_id == str(memory_id)
        ))).scalars())
        assert {row.event_type for row in events} == {"memory.vector.upsert", "memory.vector.delete"}
    await engine.dispose()
