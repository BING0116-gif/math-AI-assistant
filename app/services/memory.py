from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import hashlib
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class EventClassification:
    """LLM 分类结果"""
    event_type: str = "question"
    category: str = ""
    difficulty: int = 3
    importance: float = 0.5
    is_milestone: bool = False
    tags: List[str] = field(default_factory=list)


@dataclass
class MemoryItem:
    id: str
    content: str
    memory_type: str
    category: str
    importance: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    access_count: int = 0
    ttl_seconds: int = 3600
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds == 0:
            return False
        return datetime.now(timezone.utc) > self.created_at + timedelta(
            seconds=self.ttl_seconds
        )

    @property
    def signature(self) -> str:
        return hashlib.md5(
            f"{self.category}:{self.content[:100]}".encode()
        ).hexdigest()[:16]


class ShortTermMemory:
    capacity: int = 50
    default_ttl: int = 1800
    items: List[MemoryItem]

    def __init__(self, capacity: int = 50, default_ttl: int = 1800):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.items = []

    def add(self, item: MemoryItem) -> None:
        if item.ttl_seconds == 0:
            item.ttl_seconds = self.default_ttl

        existing = self.find_by_signature(item.signature)
        if existing:
            existing.last_accessed = datetime.now(timezone.utc)
            existing.access_count += 1
            return

        self._cleanup_expired()

        if len(self.items) >= self.capacity:
            self._evict_lru()

        self.items.append(item)

    def find_by_signature(self, signature: str) -> Optional[MemoryItem]:
        for item in self.items:
            if item.signature == signature:
                return item
        return None

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_items = []
        for item in self.items:
            if item.is_expired:
                continue

            content_lower = item.content.lower()
            content_words = set(content_lower.split())

            overlap = len(query_words & content_words)
            union = len(query_words | content_words)
            jaccard = overlap / union if union > 0 else 0

            category_bonus = 0.3 if item.category in query else 0

            recency_weight = 1.0 / (1.0 + item.access_count * 0.1)

            final_score = jaccard + category_bonus * recency_weight

            scored_items.append((item, final_score))

        scored_items.sort(key=lambda x: x[1], reverse=True)
        result = [item for item, _ in scored_items[:top_k]]

        for item in result:
            item.last_accessed = datetime.now(timezone.utc)
            item.access_count += 1

        return result

    def _cleanup_expired(self) -> int:
        before = len(self.items)
        self.items = [item for item in self.items if not item.is_expired]
        return before - len(self.items)

    def _evict_lru(self) -> None:
        if not self.items:
            return
        lru_item = min(self.items, key=lambda x: x.last_accessed)
        self.items.remove(lru_item)

    def clear(self) -> None:
        self.items.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        types_dist = {}
        for item in self.items:
            t = item.memory_type
            types_dist[t] = types_dist.get(t, 0) + 1
        return {
            "total_items": len(self.items),
            "expired_count": sum(1 for i in self.items if i.is_expired),
            "capacity_usage": f"{len(self.items)}/{self.capacity}",
            "types_distribution": types_dist,
        }


class LongTermMemory:
    def __init__(self, db_session_factory):
        self._session_factory = db_session_factory

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        from app.data.repositories import LearningRecordRepository
        from app.data.models import LearningRecord
        from sqlalchemy import select, func, and_, Integer
        from sqlalchemy.orm import sessionmaker

        async with self._session_factory() as db:
            repo = LearningRecordRepository(db)

            total_result = await db.execute(
                select(func.count()).select_from(LearningRecord).where(
                    LearningRecord.user_id == user_id
                )
            )
            total_questions = total_result.scalar() or 0

            from app.services.mastery_evidence import unique_evidence, evidence_summary
            # 旧聊天记录即使被标为正确，也不能混入答题能力统计。
            evidence = unique_evidence((await db.execute(select(LearningRecord).where(
                LearningRecord.user_id == user_id,
            ).order_by(LearningRecord.created_at, LearningRecord.id))).scalars())
            from app.data.models import PracticeAttempt
            from app.services.mastery_evidence import is_attempt_evidence
            attempts = (await db.execute(select(PracticeAttempt).where(PracticeAttempt.user_id == user_id))).scalars()
            valid_keys = {(a.session_id, a.question_id) for a in attempts if is_attempt_evidence(a)}
            evidence = [r for r in evidence if ((r.metadata_ or {}).get("session_id"), r.question_id) in valid_keys]
            correct_count = sum(r.is_correct for r in evidence)
            correct_rate = correct_count / len(evidence) if evidence else 0.0

            avg_time_result = await db.execute(
                select(func.avg(LearningRecord.time_spent)).where(
                    and_(
                        LearningRecord.user_id == user_id,
                        LearningRecord.time_spent.isnot(None),
                    )
                )
            )
            avg_time = avg_time_result.scalar() or 0

            from collections import defaultdict
            categories = defaultdict(list)
            for record in evidence:
                categories[record.category].append(record)
            weak_points, strong_points = [], []
            for category, records in categories.items():
                # 保留分类正确率算法，只对最终结果加 cap。
                summary = evidence_summary(sum(r.is_correct for r in records) / len(records), len(records))
                mastery = summary["mastery_score"]
                if mastery < 0.7:
                    weak_points.append({"category": category, "mastery": round(mastery, 2),
                                        "count": len(records), **summary})
                elif mastery > 0.85:
                    strong_points.append(category)
            weak_points.sort(key=lambda point: point["mastery"])

            if correct_rate > 0.8:
                recommended_difficulty = 5
            elif correct_rate > 0.6:
                recommended_difficulty = 4
            elif correct_rate > 0.4:
                recommended_difficulty = 3
            else:
                recommended_difficulty = 2

            recent_query = (
                select(LearningRecord)
                .where(LearningRecord.user_id == user_id)
                .order_by(LearningRecord.created_at.desc())
                .limit(10)
            )
            recent_result = await db.execute(recent_query)
            recent_records = recent_result.scalars().all()

            return {
                "total_questions": total_questions,
                "correct_rate": round(correct_rate, 2),
                "avg_time_per_question": round(avg_time, 1),
                "weak_points": weak_points[:5],
                "strong_points": strong_points[:5],
                "recommended_difficulty": recommended_difficulty,
                "recent_activity": [
                    {
                        "category": r.category,
                        "is_correct": r.is_correct,
                        "time": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in recent_records
                ],
            }

    async def get_relevant_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        from app.data.models import LearningRecord, ChatMessage, ChatSession
        from sqlalchemy import select, and_

        memories = []

        categories_in_query = self._extract_categories(query)

        async with self._session_factory() as db:
            if categories_in_query:
                error_query = (
                    select(LearningRecord)
                    .where(
                        and_(
                            LearningRecord.user_id == user_id,
                            LearningRecord.category.in_(categories_in_query),
                            LearningRecord.is_correct == False,
                        )
                    )
                    .order_by(LearningRecord.created_at.desc())
                    .limit(limit // 2)
                )
                error_result = await db.execute(error_query)
                error_records = error_result.scalars().all()

                for record in error_records:
                    date_str = (
                        record.created_at.strftime("%Y-%m-%d")
                        if record.created_at
                        else ""
                    )
                    memories.append(
                        {
                            "id": f"err_{record.id}",
                            "type": "historical_error",
                            "content": (
                                f"[{date_str}] "
                                f"你在'{record.category}'这道题上出错过。"
                                f"\n题目: {record.question_content[:80]}..."
                                f"\n错误原因: {record.error_reason or '未记录'}"
                            ),
                            "category": record.category,
                            "relevance": 0.9,
                            "timestamp": record.created_at.isoformat()
                            if record.created_at
                            else None,
                        }
                    )

            keyword = query.split()[0] if query else ""
            if keyword:
                keyword_match = f"%{keyword}%"
                chat_query = (
                    select(ChatMessage)
                    .join(ChatSession)
                    .where(
                        and_(
                            ChatSession.user_id == user_id,
                            ChatMessage.role == "assistant",
                            ChatMessage.content.ilike(keyword_match),
                        )
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(limit // 2)
                )
                chat_result = await db.execute(chat_query)
                chat_messages = chat_result.scalars().all()

                for msg in chat_messages:
                    memories.append(
                        {
                            "id": f"chat_{msg.id}",
                            "type": "conversation_memory",
                            "content": msg.content[:200],
                            "category": "",
                            "relevance": 0.7,
                            "timestamp": msg.created_at.isoformat()
                            if msg.created_at
                            else None,
                        }
                    )

        memories.sort(
            key=lambda m: (m.get("relevance", 0), m.get("timestamp", "")),
            reverse=True,
        )
        return memories[:limit]

    async def record_learning_event(
        self, event_data: Dict[str, Any]
    ) -> bool:
        try:
            from app.data.repositories import LearningRecordRepository

            async with self._session_factory() as db:
                repo = LearningRecordRepository(db)
                await repo.create(**event_data)
            return True
        except Exception as e:
            logger.error(f"记录学习事件失败: {e}")
            return False

    def _extract_categories(self, text: str) -> List[str]:
        category_keywords = {
            "积分": ["积分", "∫", "integral", "面积"],
            "导数": ["导数", "微分", "derivative", "斜率", "极限"],
            "极限": ["极限", "lim", "趋近", "无穷"],
            "级数": ["级数", "求和", "∑", "收敛", "发散"],
            "微分方程": ["微分方程", "dy/dx", "解方程"],
        }

        found_categories = []
        text_lower = text.lower()

        for category, keywords in category_keywords.items():
            if any(kw in text_lower for kw in keywords):
                found_categories.append(category)

        return found_categories

    async def _classify_event(
        self, event_data: Dict[str, Any], llm=None
    ) -> EventClassification:
        if llm is None:
            return self._classify_fallback(event_data)

        prompt = (
            "Classify this math learning event into a JSON object. "
            "Categories: 极限, 导数, 积分, 三角函数, 代数, 解析几何, 概率统计, 向量, 数列.\n\n"
            f"Content: {event_data.get('question_content', '')[:200]}\n"
            f"Tags hint: {event_data.get('sub_categories', '')}\n\n"
            'Return ONLY: {"event_type":"question|answer|clarification|error_correction|review",'
            '"category":"<one of above>","difficulty":<1-5>,"importance":<0.0-1.0>,'
            '"is_milestone":<true|false>,"tags":["tag1","tag2"]}'
        )

        try:
            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            text = response.content.strip()

            import re as _regex
            match = _regex.search(r"\{.*\}", text, _regex.DOTALL)
            if match:
                data = json.loads(match.group())
                return EventClassification(
                    event_type=data.get("event_type", "question"),
                    category=data.get("category", ""),
                    difficulty=int(data.get("difficulty", 3)),
                    importance=float(data.get("importance", 0.5)),
                    is_milestone=data.get("is_milestone", False),
                    tags=data.get("tags", []),
                )
        except Exception as e:
            logger.warning(f"LLM 事件分类失败，降级到关键词匹配: {e}")

        return self._classify_fallback(event_data)

    def _classify_fallback(
        self, event_data: Dict[str, Any]
    ) -> EventClassification:
        text = (
            event_data.get("question_content", "")
            + " "
            + event_data.get("sub_categories", "")
        )
        categories = self._extract_categories(text)

        return EventClassification(
            event_type=(
                "answer"
                if event_data.get("is_correct") is not None
                else "question"
            ),
            category=categories[0] if categories else "",
            difficulty=event_data.get("difficulty", 3),
            importance=0.5,
            is_milestone=False,
            tags=categories,
        )


@dataclass
class RetrievalResult:
    memory: MemoryItem
    score: float
    source: str
    explanation: str


class MemoryRetrievalEngine:
    def __init__(
        self,
        short_term_memory: ShortTermMemory,
        long_term_memory: LongTermMemory,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.short_term = short_term_memory
        self.long_term = long_term
        self.weights = weights or {
            "short_term": 0.4,
            "long_term": 0.6,
        }

    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> List[RetrievalResult]:
        short_term_results, long_term_results = await asyncio.gather(
            self._retrieve_from_short_term(query, top_k * 2),
            self._retrieve_from_long_term(user_id, query, top_k * 2),
        )

        all_results = []

        for item, score in short_term_results:
            all_results.append(
                RetrievalResult(
                    memory=item,
                    score=score * self.weights["short_term"],
                    source="short_term",
                    explanation=f"来自当前会话的记忆 (相关性: {score:.2f})",
                )
            )

        for item_dict in long_term_results:
            item = MemoryItem(
                id=item_dict.get("id", ""),
                content=item_dict.get("content", ""),
                memory_type=item_dict.get("type", "fact"),
                category=item_dict.get("category", ""),
                importance=item_dict.get("relevance", 0.5),
            )
            all_results.append(
                RetrievalResult(
                    memory=item,
                    score=item_dict.get("relevance", 0)
                    * self.weights["long_term"],
                    source="long_term",
                    explanation=item_dict.get("content", "")[:100],
                )
            )

        unique_results = self._deduplicate(all_results)
        filtered = [r for r in unique_results if r.score >= min_score]
        filtered.sort(key=lambda x: x.score, reverse=True)
        return filtered[:top_k]

    async def _retrieve_from_short_term(
        self, query: str, top_k: int
    ) -> List[Tuple[MemoryItem, float]]:
        items = self.short_term.retrieve(query, top_k=top_k)
        return [(item, 0.9) for item in items]

    async def _retrieve_from_long_term(
        self, user_id: str, query: str, top_k: int
    ) -> List[Dict[str, Any]]:
        return await self.long_term.get_relevant_memories(
            user_id=user_id, query=query, limit=top_k
        )

    def _deduplicate(
        self, results: List[RetrievalResult], threshold: float = 0.8
    ) -> List[RetrievalResult]:
        if not results:
            return results

        unique = [results[0]]

        for result in results[1:]:
            is_duplicate = False
            for existing in unique:
                similarity = self._text_similarity(
                    result.memory.content, existing.memory.content
                )
                if similarity > threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(result)

        return unique

    def _text_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0