"""Side-effect-free dependency diagnostics for readiness endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config.settings import settings
from app.services.embedding_service import get_embedding_service


def _vector_size(vectors: Any) -> int | None:
    """Read the configured vector size across qdrant-client response versions."""
    if vectors is None:
        return None
    if isinstance(vectors, dict):
        if not vectors:
            return None
        vectors = next(iter(vectors.values()))
    size = getattr(vectors, "size", None)
    if size is None and isinstance(vectors, dict):
        size = vectors.get("size")
    return int(size) if size is not None else None


def _qdrant_error_code(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(token in text for token in ("connection", "connecterror", "refused", "timed out", "timeout", "unreachable")):
        return "network_unreachable"
    return "probe_failed"


async def vector_dependency_health() -> dict[str, Any]:
    """Describe Embedding and Qdrant state without creating or changing a collection."""
    embedding = get_embedding_service().health()
    result: dict[str, Any] = {
        "status": "healthy",
        "code": "ready",
        "embedding": embedding,
        "qdrant": {
            "host": settings.QDRANT_HOST,
            "port": settings.QDRANT_PORT,
            "collection": settings.QUESTION_QDRANT_COLLECTION,
            "expected_vector_size": settings.VECTOR_SIZE,
        },
    }
    if embedding.get("status") != "healthy":
        result.update(status="degraded", code="embedding_unavailable")
        return result

    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3)
        collections = await asyncio.to_thread(client.get_collections)
        names = {row.name for row in collections.collections}
        if settings.QUESTION_QDRANT_COLLECTION not in names:
            result.update(status="degraded", code="collection_missing")
            result["qdrant"]["available"] = True
            return result

        info = await asyncio.to_thread(client.get_collection, settings.QUESTION_QDRANT_COLLECTION)
        actual_size = _vector_size(getattr(getattr(info, "config", None), "params", None).vectors)
        result["qdrant"].update(
            available=True,
            actual_vector_size=actual_size,
            points_count=int(getattr(info, "points_count", 0) or 0),
        )
        if actual_size != settings.VECTOR_SIZE:
            result.update(status="degraded", code="vector_dimension_mismatch")
        return result
    except Exception as exc:
        result.update(status="degraded", code=_qdrant_error_code(exc), error=str(exc)[:500])
        result["qdrant"]["available"] = False
        return result
