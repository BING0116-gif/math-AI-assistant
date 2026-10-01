import asyncio

import pytest

from app.services.memory_policy import (
    DECAY_LAMBDA,
    MEMORY_INIT_STRENGTH,
    MEMORY_TTL,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_PROFILE,
    build_embedding_summary,
)
from app.services.memory_store import (
    DECAY_LAMBDA as LEGACY_DECAY_LAMBDA,
    MEMORY_INIT_STRENGTH as LEGACY_MEMORY_INIT_STRENGTH,
    MEMORY_TTL as LEGACY_MEMORY_TTL,
    MemoryStore,
)


def test_memory_policy_old_import_path_remains_compatible():
    assert LEGACY_DECAY_LAMBDA is DECAY_LAMBDA
    assert LEGACY_MEMORY_INIT_STRENGTH is MEMORY_INIT_STRENGTH
    assert LEGACY_MEMORY_TTL is MEMORY_TTL


def test_embedding_summary_rules_keep_type_specific_bounds():
    content = "x" * 200
    assert build_embedding_summary(content, MEMORY_TYPE_ERROR) == "错题: " + "x" * 150
    assert build_embedding_summary(content, MEMORY_TYPE_PROFILE) == "画像: " + "x" * 50
    assert build_embedding_summary(content, "unknown") == "x" * 150


def test_store_summary_method_delegates_to_policy():
    store = MemoryStore.__new__(MemoryStore)
    result = asyncio.run(
        store._generate_embedding_summary("极限定义", MEMORY_TYPE_ERROR, {"ignored": True})
    )
    assert result == "错题: 极限定义"


@pytest.mark.asyncio
async def test_vector_sync_enqueues_stable_outbox_event(monkeypatch):
    captured = {}

    async def fake_enqueue(db, **kwargs):
        captured["db"] = db
        captured.update(kwargs)

    monkeypatch.setattr("app.services.outbox.enqueue_outbox", fake_enqueue)
    db = object()

    await MemoryStore.__new__(MemoryStore)._sync_to_qdrant(
        db=db,
        memory_id=42,
        user_id="student-7",
        status="active",
        expire_at=1234,
    )

    assert captured == {
        "db": db,
        "event_type": "memory.vector.upsert",
        "aggregate_type": "memory",
        "aggregate_id": "42",
        "user_id": "student-7",
        "idempotency_key": "memory-vector-upsert:42:active:1234",
    }


@pytest.mark.asyncio
async def test_internal_strength_update_forwards_user_ownership(monkeypatch):
    from app.api import memory_internal_api

    calls = []

    class FakeStore:
        async def update_memory_access(self, memory_id, *, user_id=None):
            calls.append((memory_id, user_id))
            return memory_id == 7

    monkeypatch.setattr(memory_internal_api, "require_internal_auth", lambda request: None)
    monkeypatch.setattr(memory_internal_api, "get_memory_store", FakeStore)

    result = await memory_internal_api.internal_update_strength(
        object(),
        {"user_id": "student-1", "memory_ids": [7, 8]},
    )

    assert calls == [(7, "student-1"), (8, "student-1")]
    assert result["data"] == {"updated_count": 1, "total": 2}


@pytest.mark.asyncio
async def test_active_memory_helper_returns_list_contract(monkeypatch):
    captured = {}
    expected = [{"id": 1}, {"id": 2}]

    async def fake_get_user_memories(self, **kwargs):
        captured.update(kwargs)
        return expected, 2

    monkeypatch.setattr(MemoryStore, "get_user_memories", fake_get_user_memories)

    result = await MemoryStore.__new__(MemoryStore).get_active_memories_by_user(
        "student-2",
        memory_type="error",
    )

    assert result is expected
    assert captured == {
        "user_id": "student-2",
        "memory_type": "error",
        "status": "active",
        "limit": 1000,
    }
