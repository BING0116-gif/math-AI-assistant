"""
向量数据库模块 — 基于 ChromaDB 的题目向量存储与语义检索。

设计要点：
- ChromaDB 持久化存储（自动创建目录）
- 默认使用内置 embedding 函数（all-MiniLM-L6-v2）
- 支持语义搜索、混合搜索（向量 + 关键词 + 筛选）
- metadata 自动清理（只保留 str/int/float/bool 类型）
- 增量更新（先删后加）
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    distance: float


class VectorStoreManager:
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "math_questions",
    ):
        self.persist_directory = persist_directory or settings.VECTOR_DB_PATH
        self.collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        os.makedirs(self.persist_directory, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._initialized = True
        logger.info(f"  [向量库] ChromaDB就绪: 集合={self.collection_name}, 文档数={self._collection.count()}")

    async def add_question(self, question_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        await self.initialize()
        try:
            self._collection.add(
                ids=[question_id],
                documents=[content],
                metadatas=[self._clean_metadata(metadata)],
            )
            return True
        except Exception as e:
            logger.error(f"  [向量库] 添加题目失败: id={question_id}, error={e}")
            return False

    async def add_questions_batch(
        self, questions: List[Tuple[str, str, Dict[str, Any]]], batch_size: int = 100
    ) -> int:
        await self.initialize()
        success = 0
        for i in range(0, len(questions), batch_size):
            batch = questions[i:i + batch_size]
            try:
                self._collection.add(
                    ids=[q[0] for q in batch],
                    documents=[q[1] for q in batch],
                    metadatas=[self._clean_metadata(q[2]) for q in batch],
                )
                success += len(batch)
            except Exception as e:
                logger.error(f"  [向量库] 批量添加失败: batch={i}, error={e}")
        return success

    async def semantic_search(
        self, query: str, n_results: int = 10, where: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        await self.initialize()
        try:
            results = self._collection.query(query_texts=[query], n_results=n_results, where=where)
            return self._format_results(results)
        except Exception as e:
            logger.error(f"  [向量库] 语义搜索失败: {e}")
            return []

    async def hybrid_search(
        self,
        query: str,
        category_filter: Optional[str] = None,
        difficulty_range: Optional[Tuple[int, int]] = None,
        n_results: int = 10,
        vector_weight: float = 0.7,
    ) -> List[VectorSearchResult]:
        await self.initialize()
        # ChromaDB only supports: equality, $in, $and, $or, $not
        # Does NOT support $gte/$lte — do post-filtering instead
        where_filter = {}
        if category_filter:
            where_filter["category"] = category_filter

        # Fetch more results than needed (for post-filtering)
        fetch_count = n_results * 5 if difficulty_range else n_results * 3
        vector_results = await self.semantic_search(
            query=query, n_results=fetch_count,
            where=where_filter if where_filter else None,
        )
        if not vector_results:
            return []

        # Post-filter by difficulty range (ChromaDB doesn't support range queries in where clause)
        if difficulty_range:
            lo, hi = difficulty_range
            vector_results = [
                vr for vr in vector_results
                if lo <= (vr.metadata.get("difficulty") or 3) <= hi
            ]

        keyword_scores = self._calculate_keyword_scores(query, vector_results)
        for vr in vector_results:
            kw_score = keyword_scores.get(vr.id, 0.0)
            vr.score = vector_weight * vr.score + (1 - vector_weight) * kw_score
        vector_results.sort(key=lambda x: x.score, reverse=True)
        return vector_results[:n_results]

    async def remove_question(self, question_id: str) -> bool:
        await self.initialize()
        try:
            self._collection.delete(ids=[question_id])
            return True
        except Exception as e:
            logger.error(f"  [向量库] 移除题目失败: {e}")
            return False

    async def update_question(
        self, question_id: str, content: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        await self.initialize()
        try:
            existing = self._collection.get(ids=[question_id])
            if existing["ids"]:
                current_content = existing["documents"][0] if existing["documents"] else ""
                current_metadata = existing["metadatas"][0] if existing["metadatas"] else {}
                self._collection.delete(ids=[question_id])
                self._collection.add(
                    ids=[question_id],
                    documents=[content if content is not None else current_content],
                    metadatas=[self._clean_metadata(metadata if metadata is not None else current_metadata)],
                )
                return True
            return False
        except Exception as e:
            logger.error(f"  [向量库] 更新题目失败: {e}")
            return False

    async def get_collection_stats(self) -> Dict[str, Any]:
        await self.initialize()
        try:
            count = self._collection.count()
            all_metadatas = self._collection.get(limit=min(count, 1000))["metadatas"]
            categories = {m["category"] for m in all_metadatas if m and "category" in m}
            difficulties = {m["difficulty"] for m in all_metadatas if m and "difficulty" in m}
            return {
                "total_documents": count,
                "categories": sorted(categories),
                "difficulty_range": (min(difficulties) if difficulties else None, max(difficulties) if difficulties else None),
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_all_ids(self) -> List[str]:
        await self.initialize()
        count = self._collection.count()
        if count == 0:
            return []
        return self._collection.get(limit=count)["ids"]

    def _format_results(self, raw_results) -> List[VectorSearchResult]:
        results = []
        if not raw_results or not raw_results["ids"]:
            return results
        for i in range(len(raw_results["ids"][0])):
            results.append(VectorSearchResult(
                id=raw_results["ids"][0][i],
                content=raw_results["documents"][0][i] if raw_results["documents"] else "",
                metadata=raw_results["metadatas"][0][i] if raw_results["metadatas"] else {},
                score=1.0 - raw_results["distances"][0][i] if raw_results["distances"] else 0.0,
                distance=raw_results["distances"][0][i] if raw_results["distances"] else 0.0,
            ))
        return results

    def _calculate_keyword_scores(self, query: str, results: List[VectorSearchResult]) -> Dict[str, float]:
        import re
        query_lower = query.lower()
        chinese_chars = set(re.findall(r'[\u4e00-\u9fff]+', query_lower))
        english_words = set(re.findall(r'[a-z]+', query_lower))
        keywords = chinese_chars | english_words
        if not keywords:
            return {}
        scores = {}
        for r in results:
            content_lower = r.content.lower()
            meta_str = json.dumps(r.metadata, ensure_ascii=False).lower()
            match_count = sum(1 for kw in keywords if kw in content_lower or kw in meta_str)
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


_vector_store_instance: Optional[VectorStoreManager] = None


async def get_vector_store() -> VectorStoreManager:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStoreManager()
        await _vector_store_instance.initialize()
    return _vector_store_instance