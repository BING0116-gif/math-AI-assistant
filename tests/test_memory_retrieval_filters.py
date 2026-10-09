"""回归测试：三级记忆检索的最低重要度过滤。"""

import pytest

from app.services.memory_retrieval import MemoryRetrievalEngine


class FakeMemoryStore:
    def __init__(self):
        self.vector_min_importance = None

    async def vector_search(self, **kwargs):
        self.vector_min_importance = kwargs["min_importance"]
        return [
            {
                "memory_id": 1,
                "memory_type": "conversation",
                "category": "导数",
                "importance": 0.2,
                "memory_strength": 0.8,
                "score": 0.95,
            },
            {
                "memory_id": 2,
                "memory_type": "conversation",
                "category": "导数",
                "importance": 0.8,
                "memory_strength": 0.8,
                "score": 0.95,
            },
        ]

    async def get_user_memories(self, **kwargs):
        return [
            {
                "id": 3,
                "memory_type": "error",
                "category": "导数",
                "importance": 0.2,
                "memory_strength": 0.8,
                "embedding_summary": "低重要度错题",
            },
            {
                "id": 4,
                "memory_type": "error",
                "category": "导数",
                "importance": 0.8,
                "memory_strength": 0.8,
                "embedding_summary": "高重要度错题",
            },
        ], 2


@pytest.mark.asyncio
async def test_min_importance_filters_all_retrieval_levels():
    engine = MemoryRetrievalEngine()
    store = FakeMemoryStore()
    engine._store = store

    response = await engine.retrieve(
        user_id="user-1",
        query_text="导数",
        min_importance=0.7,
        short_term_memories=[
            {
                "id": 5,
                "content": "导数低重要度记忆",
                "category": "导数",
                "importance": 0.2,
            },
            {
                "id": 6,
                "content": "导数高重要度记忆",
                "category": "导数",
                "importance": 0.8,
            },
        ],
    )

    assert store.vector_min_importance == 0.7
    assert response.memories
    assert all(memory.importance >= 0.7 for memory in response.memories)
    assert {memory.id for memory in response.memories} == {2, 4, 6}


@pytest.mark.asyncio
async def test_invalid_min_importance_keeps_legacy_unfiltered_behavior():
    engine = MemoryRetrievalEngine()
    store = FakeMemoryStore()
    engine._store = store

    response = await engine.retrieve(
        user_id="user-1",
        query_text="导数",
        min_importance="not-a-number",
    )

    assert store.vector_min_importance == 0.0
    assert any(memory.importance == 0.2 for memory in response.memories)
