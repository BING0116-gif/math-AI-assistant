"""Single local embedding runtime shared by question and memory vectors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.model_name = settings.VECTOR_EMBEDDING_MODEL
        self.vector_size = settings.VECTOR_SIZE
        self._model: Any = None
        self._lock = asyncio.Lock()
        self._error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def error(self) -> str | None:
        return self._error

    async def initialize(self) -> None:
        if self.ready:
            return
        async with self._lock:
            if self.ready:
                return
            try:
                from sentence_transformers import SentenceTransformer
                model = await asyncio.wait_for(
                    asyncio.to_thread(SentenceTransformer, self.model_name), timeout=120
                )
                dimension_getter = getattr(model, "get_embedding_dimension", None)
                dimension = int(
                    dimension_getter() if dimension_getter else model.get_sentence_embedding_dimension()
                )
                if dimension != self.vector_size:
                    raise RuntimeError(
                        f"embedding dimension mismatch: model={dimension}, configured={self.vector_size}"
                    )
                self._model = model
                self._error = None
                logger.info("Embedding 模型已就绪: %s (%s维)", self.model_name, dimension)
            except Exception as exc:
                self._model = None
                self._error = str(exc)
                logger.warning("Embedding 模型初始化失败: %s", exc)
                raise RuntimeError("embedding model unavailable") from exc

    def encode(self, text: str) -> list[float]:
        if not self.ready:
            raise RuntimeError("embedding model is not ready")
        vector = self._model.encode(str(text), normalize_embeddings=True).tolist()
        if len(vector) != self.vector_size:
            raise RuntimeError("embedding output dimension mismatch")
        return vector

    async def encode_async(self, text: str) -> list[float]:
        await self.initialize()
        return await asyncio.to_thread(self.encode, text)

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.ready else "degraded",
            "model": self.model_name,
            "vector_size": self.vector_size,
            "error": self._error,
        }


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
