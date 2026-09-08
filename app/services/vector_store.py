"""
向量数据库模块 — 基于 Qdrant 的题目向量存储与语义检索。

设计要点：
- Qdrant 高性能向量搜索（Rust 编写，延迟低、吞吐高）
- 支持语义搜索、混合搜索（向量 + 关键词 + 筛选）
- payload 过滤在 ANN 前应用（召回率稳定）
- 支持量化技术（可选，减少内存占用）
- 降级策略：Qdrant 不可用时自动降级到内存模式
- 重试机制：初始化失败自动重试 3 次
- Embedding 模型集成：SentenceTransformer 自动生成向量
"""

from __future__ import annotations

import os

import asyncio
import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


QDRANT_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _to_qdrant_id(question_id: str) -> uuid.UUID:
    return uuid.uuid5(QDRANT_UUID_NAMESPACE, question_id)

logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        Range,
        QuantizationConfig,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("[向量库] qdrant-client 未安装，将使用内存模式降级")

from app.config.settings import settings
from app.services.embedding_service import get_embedding_service


class VectorStoreStatus(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    DEGRADED = "degraded"


@dataclass
class VectorSearchResult:
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    distance: float


class QdrantVectorStoreManager:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
        use_quantization: bool = False,
        embedder_model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        availability_check_interval: float = 30.0,
    ):
        self.host = host or settings.QDRANT_HOST
        self.port = port or settings.QDRANT_PORT
        self.collection_name = collection_name or settings.QUESTION_QDRANT_COLLECTION
        self.vector_size = vector_size or settings.VECTOR_SIZE
        self.use_quantization = use_quantization
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.availability_check_interval = availability_check_interval

        self._client: Optional[Any] = None
        self._status = VectorStoreStatus.INITIALIZING
        self._last_availability_check: float = 0
        self._is_available: bool = False

        self._embedding = get_embedding_service()
        self._embedder_model = embedder_model or settings.VECTOR_EMBEDDING_MODEL

        self._in_memory_points: Dict[str, PointStruct] = {}
        self._use_memory_fallback: bool = False

    async def initialize(self) -> None:
        if self._status == VectorStoreStatus.READY:
            return

        self._status = VectorStoreStatus.INITIALIZING
        logger.info("[向量库] 开始初始化...")

        embedding_ready = False
        try:
            await self._init_embedder()
            embedding_ready = True
        except Exception as exc:
            self._status = VectorStoreStatus.DEGRADED
            self._is_available = False
            logger.warning("[向量库] embedding 不可用，Qdrant 保持降级: %s", exc)

        if not embedding_ready:
            return

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if not QDRANT_AVAILABLE:
                    raise ImportError("qdrant-client 未安装")

                self._client = QdrantClient(host=self.host, port=self.port)

                collections = self._client.get_collections()
                exists = any(
                    c.name == self.collection_name for c in collections.collections
                )

                if not exists:
                    self._create_collection()

                collection_info = self._client.get_collection(self.collection_name)
                logger.info(
                    f"[向量库] Qdrant 就绪: collection={self.collection_name}, "
                    f"points={collection_info.points_count}, "
                    f"status={collection_info.status}"
                )

                self._status = VectorStoreStatus.READY
                self._is_available = True
                self._use_memory_fallback = False
                self._last_availability_check = time.time()
                return

            except Exception as e:
                last_error = e
                logger.warning(
                    f"[向量库] 初始化失败（第 {attempt + 1}/{self.max_retries} 次）: {e}"
                )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

        logger.error(
            f"[向量库] 初始化失败，已重试 {self.max_retries} 次，"
            f"保持显式降级状态: {last_error}"
        )

        self._status = VectorStoreStatus.DEGRADED
        self._is_available = False
        self._use_memory_fallback = False

    async def _init_embedder(self) -> None:
        await self._embedding.initialize()

    def _create_collection(self) -> None:
        if not self._client:
            return

        vector_config = VectorParams(
            size=self.vector_size,
            distance=Distance.COSINE,
        )

        quantization_config = None
        if self.use_quantization:
            quantization_config = QuantizationConfig(
                scalar=ScalarQuantization(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            )

        self._client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=vector_config,
            quantization_config=quantization_config,
        )
        logger.info(f"[向量库] Qdrant collection 创建: {self.collection_name}")

    async def check_availability(self) -> bool:
        now = time.time()
        if now - self._last_availability_check < self.availability_check_interval:
            return self._is_available

        self._last_availability_check = now

        try:
            await self._embedding.initialize()
            if self._client is None:
                self._client = QdrantClient(host=self.host, port=self.port)
            collections = self._client.get_collections()
            if not any(row.name == self.collection_name for row in collections.collections):
                self._create_collection()
            self._is_available = True
            self._use_memory_fallback = False
            if self._status != VectorStoreStatus.READY:
                self._status = VectorStoreStatus.READY
                logger.info("[向量库] Qdrant 与 embedding 已恢复")
        except Exception as e:
            logger.warning(f"[向量库] Qdrant 不可用: {e}")
            self._is_available = False
            if self._status == VectorStoreStatus.READY:
                self._status = VectorStoreStatus.DEGRADED
                logger.warning("[向量库] 降级到内存模式")

        return self._is_available

    def _generate_vector(self, text: str) -> List[float]:
        return self._embedding.encode(text)

    @property
    def status(self) -> VectorStoreStatus:
        return self._status

    @property
    def is_available(self) -> bool:
        return self._is_available

    @property
    def is_degraded(self) -> bool:
        return self._status == VectorStoreStatus.DEGRADED

    async def add_question(
        self,
        question_id: str,
        content: str,
        metadata: Dict[str, Any],
        vector: Optional[List[float]] = None,
    ) -> bool:
        await self.initialize()

        if not await self.check_availability():
            raise RuntimeError("qdrant unavailable")

        if vector is None:
            vector = self._generate_vector(content)

        if self._use_memory_fallback:
            return self._memory_add(question_id, content, metadata, vector)

        try:
            payload = self._clean_metadata(metadata)
            payload["question_id"] = question_id

            point = PointStruct(
                id=_to_qdrant_id(question_id),
                vector=vector,
                payload=payload,
            )

            self._client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )

            return True

        except Exception as e:
            logger.error(
                f"[向量库] 添加题目失败: id={question_id}, error={e}\n"
                f"{traceback.format_exc()}"
            )
            return False

    async def add_questions_batch(
        self,
        questions: List[Tuple[str, str, Dict[str, Any], Optional[List[float]]]],
        batch_size: int = 100,
    ) -> int:
        await self.initialize()
        if not await self.check_availability():
            raise RuntimeError("qdrant unavailable")
        success = 0

        for i in range(0, len(questions), batch_size):
            batch = questions[i : i + batch_size]
            points = []

            for question_id, content, metadata, vector in batch:
                if vector is None:
                    vector = self._generate_vector(content)

                if self._use_memory_fallback:
                    if self._memory_add(question_id, content, metadata, vector):
                        success += 1
                    continue

                payload = self._clean_metadata(metadata)
                payload["question_id"] = question_id

                points.append(
                    PointStruct(
                        id=_to_qdrant_id(question_id),
                        vector=vector,
                        payload=payload,
                    )
                )

            if points and not self._use_memory_fallback:
                try:
                    self._client.upsert(
                        collection_name=self.collection_name,
                        points=points,
                    )
                    success += len(batch)
                except Exception as e:
                    logger.error(
                        f"[向量库] 批量添加失败: batch={i}, error={e}\n"
                        f"{traceback.format_exc()}"
                    )

        return success

    async def semantic_search(
        self,
        query_vector: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        await self.initialize()
        await self.check_availability()

        if not self._is_available:
            raise RuntimeError("qdrant unavailable")

        try:
            filter_obj = self._build_filter(where)

            response = self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=n_results,
                query_filter=filter_obj,
                with_payload=True,
            )

            return self._format_results(response.points)

        except Exception as e:
            logger.error(
                f"[向量库] 语义搜索失败: {e}\n{traceback.format_exc()}"
            )
            return []

    async def hybrid_search(
        self,
        query_vector: List[float],
        query_text: str,
        category_filter: Optional[str] = None,
        difficulty_range: Optional[Tuple[int, int]] = None,
        n_results: int = 10,
        vector_weight: float = 0.7,
    ) -> List[VectorSearchResult]:
        await self.initialize()

        where_filter = {}
        if category_filter:
            where_filter["category"] = category_filter
        if difficulty_range:
            where_filter["difficulty"] = {
                "gte": difficulty_range[0],
                "lte": difficulty_range[1],
            }

        vector_results = await self.semantic_search(
            query_vector=query_vector,
            n_results=n_results * 2,
            where=where_filter,
        )

        if not vector_results:
            return []

        keyword_scores = self._calculate_keyword_scores(query_text, vector_results)

        for vr in vector_results:
            kw_score = keyword_scores.get(vr.id, 0.0)
            vr.score = vector_weight * vr.score + (1 - vector_weight) * kw_score

        vector_results.sort(key=lambda x: x.score, reverse=True)
        return vector_results[:n_results]

    async def remove_question(self, question_id: str) -> bool:
        await self.initialize()

        if not await self.check_availability():
            raise RuntimeError("qdrant unavailable")

        if self._use_memory_fallback:
            if question_id in self._in_memory_points:
                del self._in_memory_points[question_id]
                return True
            return False

        try:
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=[_to_qdrant_id(question_id)],
            )
            return True
        except Exception as e:
            logger.error(
                f"[向量库] 移除题目失败: {e}\n{traceback.format_exc()}"
            )
            return False

    async def update_question(
        self,
        question_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        vector: Optional[List[float]] = None,
    ) -> bool:
        await self.initialize()

        if self._use_memory_fallback:
            if question_id not in self._in_memory_points:
                return False

            existing = self._in_memory_points[question_id]
            new_payload = self._clean_metadata(
                metadata if metadata else existing.payload
            )
            new_vector = vector if vector else existing.vector

            if new_vector is None and content:
                new_vector = self._generate_vector(content)

            self._in_memory_points[question_id] = PointStruct(
                id=question_id,
                vector=new_vector,
                payload=new_payload,
            )
            return True

        try:
            qid = _to_qdrant_id(question_id)
            existing = self._client.retrieve(
                collection_name=self.collection_name,
                ids=[qid],
            )

            if existing:
                current_payload = (
                    existing[0].payload if existing[0].payload else {}
                )
                current_vector = (
                    existing[0].vector if existing[0].vector else None
                )

                new_payload = self._clean_metadata(
                    metadata if metadata else current_payload
                )
                new_payload["question_id"] = question_id
                new_vector = vector if vector else current_vector

                if new_vector is None and content:
                    new_vector = self._generate_vector(content)

                point = PointStruct(
                    id=qid,
                    vector=new_vector,
                    payload=new_payload,
                )

                self._client.upsert(
                    collection_name=self.collection_name,
                    points=[point],
                )
                return True

            return False

        except Exception as e:
            logger.error(
                f"[向量库] 更新题目失败: {e}\n{traceback.format_exc()}"
            )
            return False

    async def get_collection_stats(self) -> Dict[str, Any]:
        await self.initialize()

        if self._use_memory_fallback:
            points = list(self._in_memory_points.values())
            categories = {
                p.payload.get("category")
                for p in points
                if p.payload and "category" in p.payload
            }
            difficulties = {
                p.payload.get("difficulty")
                for p in points
                if p.payload and "difficulty" in p.payload
            }

            return {
                "total_documents": len(points),
                "categories": sorted(categories),
                "difficulty_range": (
                    min(difficulties) if difficulties else None,
                    max(difficulties) if difficulties else None,
                ),
                "status": "degraded",
                "mode": "memory",
            }

        try:
            collection_info = self._client.get_collection(self.collection_name)

            points = []
            if collection_info.points_count:
                points = self._client.scroll(
                    collection_name=self.collection_name,
                    limit=min(collection_info.points_count, 1000),
                )[0]

            categories = {
                p.payload.get("category")
                for p in points
                if p.payload and "category" in p.payload
            }
            difficulties = {
                p.payload.get("difficulty")
                for p in points
                if p.payload and "difficulty" in p.payload
            }

            return {
                "total_documents": collection_info.points_count,
                "categories": sorted(categories),
                "difficulty_range": (
                    min(difficulties) if difficulties else None,
                    max(difficulties) if difficulties else None,
                ),
                "status": collection_info.status,
                "optimizer_status": collection_info.optimizer_status,
                "mode": "qdrant",
            }

        except Exception as e:
            return {"error": str(e), "mode": "error"}

    async def get_all_ids(self) -> List[str]:
        await self.initialize()

        if self._use_memory_fallback:
            return list(self._in_memory_points.keys())

        try:
            all_ids = []
            offset = None

            while True:
                points, next_offset = self._client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,
                    offset=offset,
                    with_payload=True,
                )
                for p in points:
                    payload = p.payload if p.payload else {}
                    qid = payload.get("question_id", str(p.id))
                    all_ids.append(qid)

                if next_offset is None:
                    break
                offset = next_offset

            return all_ids

        except Exception as e:
            logger.error(
                f"[向量库] 获取所有ID失败: {e}\n{traceback.format_exc()}"
            )
            return []

    async def delete_question(self, question_id: str) -> bool:
        """Protocol-compatible idempotent delete."""
        return await self.remove_question(question_id)

    def _memory_add(
        self,
        question_id: str,
        content: str,
        metadata: Dict[str, Any],
        vector: List[float],
    ) -> bool:
        point = PointStruct(
            id=question_id,
            vector=vector,
            payload=self._clean_metadata(metadata),
        )
        self._in_memory_points[question_id] = point
        return True

    def _memory_search(
        self,
        query_vector: List[float],
        n_results: int,
        where: Optional[Dict[str, Any]],
    ) -> List[VectorSearchResult]:
        candidates = []

        for qid, point in self._in_memory_points.items():
            if where and not self._memory_match_filter(point.payload, where):
                continue

            similarity = self._cosine_similarity(
                query_vector, point.vector
            )
            candidates.append((qid, point, similarity))

        candidates.sort(key=lambda x: x[2], reverse=True)
        top_k = candidates[:n_results]

        results = []
        for qid, point, score in top_k:
            results.append(
                VectorSearchResult(
                    id=str(qid),
                    content=point.payload.get("content", "") if point.payload else "",
                    metadata=point.payload if point.payload else {},
                    score=score,
                    distance=1.0 - score,
                )
            )

        return results

    def _memory_match_filter(
        self, payload: Dict[str, Any], where: Dict[str, Any]
    ) -> bool:
        for key, value in where.items():
            payload_value = payload.get(key)

            if isinstance(value, dict):
                if "gte" in value and payload_value < value["gte"]:
                    return False
                if "lte" in value and payload_value > value["lte"]:
                    return False
            else:
                if payload_value != value:
                    return False

        return True

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _build_filter(self, where: Optional[Dict[str, Any]]) -> Optional[Filter]:
        if not where:
            return None

        if not QDRANT_AVAILABLE:
            return None

        conditions = []

        for key, value in where.items():
            if isinstance(value, dict):
                if "gte" in value or "lte" in value:
                    gte = value.get("gte")
                    lte = value.get("lte")

                    conditions.append(
                        FieldCondition(
                            key=key,
                            range=Range(gte=gte, lte=lte),
                        )
                    )
            else:
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        return Filter(must=conditions) if conditions else None

    def _format_results(self, raw_results) -> List[VectorSearchResult]:
        results = []
        for r in raw_results:
            payload = r.payload if r.payload else {}
            question_id = payload.get("question_id", str(r.id))
            results.append(
                VectorSearchResult(
                    id=question_id,
                    content=payload.get("content", ""),
                    metadata=payload,
                    score=r.score,
                    distance=1.0 - r.score,
                )
            )
        return results

    def _calculate_keyword_scores(
        self, query: str, results: List[VectorSearchResult]
    ) -> Dict[str, float]:
        import re

        query_lower = query.lower()
        chinese_chars = set(re.findall(r"[\u4e00-\u9fff]+", query_lower))
        english_words = set(re.findall(r"[a-z]+", query_lower))
        keywords = chinese_chars | english_words

        if not keywords:
            return {}

        scores = {}
        for r in results:
            content_lower = r.content.lower()
            meta_str = json.dumps(r.metadata, ensure_ascii=False).lower()
            match_count = sum(
                1 for kw in keywords if kw in content_lower or kw in meta_str
            )
            scores[r.id] = match_count / len(keywords)

        return scores

    @staticmethod
    def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
            elif isinstance(v, (list, dict)):
                cleaned[k] = json.dumps(v, ensure_ascii=False)
            else:
                cleaned[k] = str(v)
        return cleaned


_qdrant_vector_store_instance: Optional[QdrantVectorStoreManager] = None


async def get_vector_store() -> QdrantVectorStoreManager:
    global _qdrant_vector_store_instance
    if _qdrant_vector_store_instance is None:
        _qdrant_vector_store_instance = QdrantVectorStoreManager(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            collection_name=settings.QUESTION_QDRANT_COLLECTION,
            vector_size=settings.VECTOR_SIZE,
            embedder_model=settings.VECTOR_EMBEDDING_MODEL,
        )
        await _qdrant_vector_store_instance.initialize()
    return _qdrant_vector_store_instance


VectorStoreManager = QdrantVectorStoreManager
