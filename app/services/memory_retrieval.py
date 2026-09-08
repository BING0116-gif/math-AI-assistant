"""
三级记忆检索引擎。

实现：
1. 三级召回：短期内存 → Qdrant 向量语义召回 → SQL 精确匹配
2. FinalScore 综合打分重排序
3. 配额裁剪（按 memory_type 限制返回上限）
4. 最终返回 ≤7 条
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.services.memory_store import (
    MemoryStore,
    get_memory_store,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_MILESTONE,
    MEMORY_TYPE_PROFILE,
    STATUS_ACTIVE,
)

logger = logging.getLogger(__name__)

# 三级召回权重系数
W1_SHORT_TERM = 0.3
W2_VECTOR = 0.5
W3_SQL = 0.2

# FinalScore 参数
ALPHA_IMPORTANCE = 0.25
BETA_STRENGTH = 0.25
GAMMA_DECAY = 0.15
DELTA_MASTERY = 0.20
DECAY_K = 0.003  # 时间衰减系数

# 配额裁剪上限
QUOTA_LIMITS = {
    MEMORY_TYPE_ERROR: 3,
    MEMORY_TYPE_CONVERSATION: 3,
    MEMORY_TYPE_MILESTONE: 2,
    MEMORY_TYPE_PROFILE: 1,  # 画像固定带入，不参与检索
}

# 最终返回上限
MAX_TOTAL_RESULTS = 7

# 最低过滤分数
MIN_SCORE_THRESHOLD = 0.3

# Qdrant 相似度阈值
QDRANT_MIN_SCORE = 0.6


@dataclass
class RetrievedMemory:
    """检索到的记忆结果。"""
    id: int
    memory_type: str
    high_category: str
    category: str
    summary: str
    importance: float
    memory_strength: float
    difficulty: Optional[int] = None
    created_at: int = 0
    last_accessed: Optional[int] = None
    access_count: int = 0
    score: float = 0.0
    source: str = ""  # short_term / vector / sql
    tags: Optional[List[str]] = None


@dataclass
class RetrievalResponse:
    """检索响应。"""
    memories: List[RetrievedMemory] = field(default_factory=list)
    total: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)


class MemoryRetrievalEngine:
    """三级记忆检索引擎。"""

    def __init__(self):
        self._store: Optional[MemoryStore] = None

    async def _get_store(self) -> MemoryStore:
        if self._store is None:
            self._store = get_memory_store()
        return self._store

    async def retrieve(
        self,
        user_id: str,
        query_text: str,
        top_k: int = MAX_TOTAL_RESULTS,
        memory_types: Optional[List[str]] = None,
        high_category: Optional[str] = None,
        min_importance: float = 0.0,
        short_term_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> RetrievalResponse:
        """三级召回主入口。

        Args:
            user_id: 用户 ID
            query_text: 查询文本
            top_k: 最终返回条数
            memory_types: 可选记忆类型过滤
            high_category: 可选一级分类过滤
            min_importance: 最低重要度过滤
            short_term_memories: 短期记忆列表（由外部传入）

        Returns:
            RetrievalResponse: 检索结果
        """
        # 提取元信息
        categories = self._extract_categories(query_text)

        # 并行执行三级召回
        level1_task = self._retrieve_short_term(
            short_term_memories or [], query_text, categories
        )
        level2_task = self._retrieve_vector(
            user_id, query_text, memory_types, high_category
        )
        level3_task = self._retrieve_sql(
            user_id, categories, memory_types, high_category
        )

        level1_results, level2_results, level3_results = await asyncio.gather(
            level1_task, level2_task, level3_task
        )

        # 合并候选池
        all_candidates: List[RetrievedMemory] = []
        seen_ids: set = set()

        for mem in level1_results:
            dedup_key = f"short_term_{mem.id}"
            if dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                all_candidates.append(mem)

        for mem in level2_results:
            dedup_key = f"vector_{mem.id}"
            if dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                all_candidates.append(mem)

        for mem in level3_results:
            dedup_key = f"sql_{mem.id}"
            if dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                all_candidates.append(mem)

        logger.info(
            f"[记忆检索] 三级召回完成: level1={len(level1_results)}, "
            f"level2={len(level2_results)}, level3={len(level3_results)}, "
            f"合并后={len(all_candidates)}"
        )

        # FinalScore 综合打分
        scored = self._final_score(all_candidates, query_text)

        # 过滤低分
        filtered = [m for m in scored if m.score >= MIN_SCORE_THRESHOLD]

        # 按分数降序排列
        filtered.sort(key=lambda x: x.score, reverse=True)

        # 配额裁剪
        cropped = self._quota_crop(filtered)

        # 最终截断
        final = cropped[:top_k]

        stats = {
            "level1_count": len(level1_results),
            "level2_count": len(level2_results),
            "level3_count": len(level3_results),
            "candidates": len(all_candidates),
            "filtered": len(filtered),
            "final": len(final),
        }

        return RetrievalResponse(memories=final, total=len(final), stats=stats)

    # ========================================================================
    # 第一级：短期记忆召回
    # ========================================================================

    async def _retrieve_short_term(
        self,
        short_term_memories: List[Dict[str, Any]],
        query_text: str,
        categories: List[str],
    ) -> List[RetrievedMemory]:
        """第一级：从短期记忆中召回（最多 8 条）。"""
        results = []
        query_lower = query_text.lower()
        query_words = set(query_lower.split())

        for item in short_term_memories[:8]:
            content = item.get("content", "")
            content_lower = content.lower()
            content_words = set(content_lower.split())

            # Jaccard 相似度
            overlap = len(query_words & content_words)
            union = len(query_words | content_words)
            jaccard = overlap / union if union > 0 else 0

            category_bonus = 0.0
            item_cat = item.get("category", "")
            if item_cat in categories or any(c in query_lower for c in [item_cat]):
                category_bonus = 0.3

            score = jaccard * 0.7 + category_bonus * 0.3

            if score > 0:
                results.append(RetrievedMemory(
                    id=item.get("id", 0),
                    memory_type=item.get("memory_type", MEMORY_TYPE_CONVERSATION),
                    high_category=item.get("high_category", ""),
                    category=item.get("category", ""),
                    summary=content[:200],
                    importance=item.get("importance", 0.5),
                    memory_strength=item.get("memory_strength", 0.6),
                    difficulty=item.get("difficulty"),
                    created_at=item.get("created_at", 0),
                    score=score,
                    source="short_term",
                ))

        return results

    # ========================================================================
    # 第二级：Qdrant 向量语义召回
    # ========================================================================

    async def _retrieve_vector(
        self,
        user_id: str,
        query_text: str,
        memory_types: Optional[List[str]] = None,
        high_category: Optional[str] = None,
    ) -> List[RetrievedMemory]:
        """第二级：Qdrant 向量语义召回（Top-20）。"""
        store = await self._get_store()
        results = await store.vector_search(
            user_id=user_id,
            query_text=query_text,
            top_k=20,
            memory_types=memory_types,
            high_category=high_category,
            min_score=QDRANT_MIN_SCORE,
        )

        retrieved = []
        for r in results:
            retrieved.append(RetrievedMemory(
                id=r.get("memory_id", 0),
                memory_type=r.get("memory_type", ""),
                high_category=r.get("high_category", ""),
                category=r.get("category", ""),
                summary=r.get("summary", ""),
                importance=r.get("importance", 0.5),
                memory_strength=r.get("memory_strength", 0.5),
                difficulty=r.get("difficulty"),
                created_at=r.get("created_at", 0),
                last_accessed=r.get("last_accessed", 0),
                access_count=r.get("access_count", 0),
                score=r.get("score", 0.0),
                source="vector",
            ))

        return retrieved

    # ========================================================================
    # 第三级：SQL 精确匹配
    # ========================================================================

    async def _retrieve_sql(
        self,
        user_id: str,
        categories: List[str],
        memory_types: Optional[List[str]] = None,
        high_category: Optional[str] = None,
    ) -> List[RetrievedMemory]:
        """第三级：SQL 精确匹配（关键词/错题标签，最多 10 条）。"""
        store = await self._get_store()
        memories, _ = await store.get_user_memories(
            user_id=user_id,
            memory_type=None,
            status=STATUS_ACTIVE,
            limit=100,
        )

        results = []
        for mem in memories:
            score = 0.0

            # 知识点匹配
            mem_cat = mem.get("category", "")
            if mem_cat in categories:
                score += 0.5

            # 一级分类匹配
            mem_high = mem.get("high_category", "")
            if high_category and mem_high == high_category:
                score += 0.3

            # 标签匹配
            tags = mem.get("tags", "") or ""
            if isinstance(tags, str):
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tag_list = tags

            if categories:
                for cat in categories:
                    if any(cat in tag for tag in tag_list):
                        score += 0.2
                        break

            if score > 0:
                results.append(RetrievedMemory(
                    id=mem.get("id", 0),
                    memory_type=mem.get("memory_type", ""),
                    high_category=mem.get("high_category", ""),
                    category=mem.get("category", ""),
                    summary=mem.get("embedding_summary", "")[:200],
                    importance=float(mem.get("importance", 0.5)),
                    memory_strength=float(mem.get("memory_strength", 0.5)),
                    difficulty=mem.get("difficulty"),
                    created_at=int(mem.get("created_at", 0)),
                    last_accessed=int(mem.get("last_accessed", 0)) if mem.get("last_accessed") else None,
                    access_count=int(mem.get("access_count", 0)),
                    score=score,
                    source="sql",
                    tags=tag_list,
                ))

        # 按分数排序取前 10
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:10]

    # ========================================================================
    # FinalScore 综合打分
    # ========================================================================

    def _final_score(
        self,
        candidates: List[RetrievedMemory],
        query_text: str,
        mastery_data: Optional[Dict[str, float]] = None,
    ) -> List[RetrievedMemory]:
        """FinalScore 综合打分重排序。

        FinalScore = w1·S_short + w2·S_vector + w3·S_sql
                    + α·importance + β·memory_strength
                    - γ·time_decay - δ·mastery_bonus
        """
        now = time.time()

        for mem in candidates:
            base_score = 0.0

            # 召回分数加权
            if mem.source == "short_term":
                base_score += W1_SHORT_TERM * mem.score
            elif mem.source == "vector":
                base_score += W2_VECTOR * mem.score
            elif mem.source == "sql":
                base_score += W3_SQL * mem.score

            # 重要度加分
            base_score += ALPHA_IMPORTANCE * mem.importance

            # 记忆强度加分
            base_score += BETA_STRENGTH * mem.memory_strength

            # 时间衰减
            if mem.created_at > 0:
                days_elapsed = (now - mem.created_at) / 86400.0
                time_decay = math.exp(-DECAY_K * days_elapsed)
                base_score -= GAMMA_DECAY * (1.0 - time_decay)

            # 掌握度修正（高掌握度扣分，加速已掌握内容衰减）
            if mastery_data and mem.category in mastery_data:
                correct_rate = mastery_data[mem.category]
                if correct_rate >= 0.7:
                    base_score -= DELTA_MASTERY * correct_rate

            mem.score = max(0.0, min(1.0, base_score))

        return candidates

    # ========================================================================
    # 配额裁剪
    # ========================================================================

    def _quota_crop(
        self, memories: List[RetrievedMemory]
    ) -> List[RetrievedMemory]:
        """按 memory_type 配额裁剪。"""
        type_counts: Dict[str, int] = {}
        result = []

        for mem in memories:
            mtype = mem.memory_type
            limit = QUOTA_LIMITS.get(mtype, MAX_TOTAL_RESULTS)
            current = type_counts.get(mtype, 0)

            if current < limit:
                result.append(mem)
                type_counts[mtype] = current + 1

        return result

    # ========================================================================
    # 工具方法
    # ========================================================================

    def _extract_categories(self, text: str) -> List[str]:
        """从文本中提取知识点分类。"""
        category_keywords = {
            "极限": ["极限", "lim", "趋近", "无穷", "收敛"],
            "导数": ["导数", "微分", "derivative", "斜率", "求导"],
            "积分": ["积分", "∫", "integral", "面积", "原函数", "不定积分", "定积分"],
            "级数": ["级数", "求和", "∑", "收敛", "发散", "审敛"],
            "微分方程": ["微分方程", "dy/dx", "解方程", "通解", "特解"],
            "矩阵": ["矩阵", "行列式", "特征值", "特征向量", "线性变换"],
            "概率": ["概率", "分布", "期望", "方差", "随机"],
            "向量": ["向量", "点积", "叉积", "线性相关"],
        }

        found = []
        text_lower = text.lower()
        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                found.append(category)

        return found


# 全局单例
_retrieval_engine_instance: Optional[MemoryRetrievalEngine] = None


def get_retrieval_engine() -> MemoryRetrievalEngine:
    global _retrieval_engine_instance
    if _retrieval_engine_instance is None:
        _retrieval_engine_instance = MemoryRetrievalEngine()
    return _retrieval_engine_instance