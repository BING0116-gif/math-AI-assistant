"""Qdrant index for active student memories."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config.settings import settings
from app.services.embedding_service import get_embedding_service


class MemoryVectorStore:
    def __init__(self) -> None:
        self._client: Any = None
        self._embedding = get_embedding_service()

    async def initialize(self) -> None:
        await self._embedding.initialize()
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
            collections = await asyncio.to_thread(self._client.get_collections)
            if not any(row.name == settings.MEMORY_QDRANT_COLLECTION for row in collections.collections):
                await asyncio.to_thread(
                    self._client.create_collection,
                    collection_name=settings.MEMORY_QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=settings.VECTOR_SIZE, distance=Distance.COSINE),
                )

    async def upsert(self, memory: Any) -> None:
        from qdrant_client.models import PointStruct
        await self.initialize()
        vector = await self._embedding.encode_async(memory.embedding_summary)
        payload = {
            "memory_id": memory.id,
            "user_id": memory.user_id,
            "memory_type": memory.memory_type,
            "high_category": memory.high_category,
            "category": memory.category,
            "importance": memory.importance,
            "difficulty": memory.difficulty,
            "status": memory.status,
            "expire_at": memory.expire_at,
            "memory_strength": memory.memory_strength,
            "source_id": memory.source_id or "",
        }
        await asyncio.to_thread(
            self._client.upsert,
            collection_name=settings.MEMORY_QDRANT_COLLECTION,
            points=[PointStruct(id=memory.id, vector=vector, payload=payload)],
        )

    async def delete(self, memory_id: int) -> None:
        await self.initialize()
        await asyncio.to_thread(
            self._client.delete,
            collection_name=settings.MEMORY_QDRANT_COLLECTION,
            points_selector=[memory_id],
        )


_memory_vector_store: MemoryVectorStore | None = None


def get_memory_vector_store() -> MemoryVectorStore:
    global _memory_vector_store
    if _memory_vector_store is None:
        _memory_vector_store = MemoryVectorStore()
    return _memory_vector_store
