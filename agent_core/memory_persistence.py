from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.memory import (
    LongTermMemory,
    MemoryRetrievalEngine,
    ShortTermMemory,
    MemoryItem,
)
from app.services.event_buffer import EnhancedEventBuffer
from app.data.database import get_db_session

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户画像（扩展版），包含原有统计字段 + Skill 字段 + 错误模式"""

    total_questions: int = 0
    correct_rate: float = 0.0
    avg_time_per_question: float = 0.0
    weak_points: List[Dict[str, Any]] = field(default_factory=list)
    strong_points: List[str] = field(default_factory=list)
    recommended_difficulty: int = 3
    recent_activity: List[Dict[str, Any]] = field(default_factory=list)

    skills: List[Dict[str, Any]] = field(default_factory=list)

    error_patterns: List[Dict[str, Any]] = field(default_factory=list)

    cognitive_style: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_questions": self.total_questions,
            "correct_rate": self.correct_rate,
            "avg_time_per_question": self.avg_time_per_question,
            "weak_points": self.weak_points,
            "strong_points": self.strong_points,
            "recommended_difficulty": self.recommended_difficulty,
            "recent_activity": self.recent_activity,
            "skills": self.skills,
            "error_patterns": self.error_patterns,
            "cognitive_style": self.cognitive_style,
        }

    def to_compact_json(self, max_length: int = 800) -> str:
        compact = {
            "cr": self.correct_rate,
            "wp": [
                {"c": w["category"], "m": w["mastery"]}
                for w in self.weak_points
            ],
            "s": [
                {
                    "c": s["skill_code"],
                    "m": s["mastery_level"],
                    "st": s["status"][0],
                }
                for s in self.skills
            ],
            "ep": [
                {"p": e["pattern"], "f": e["frequency"]}
                for e in self.error_patterns
            ],
        }
        text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(text) > max_length:
            while len(text) > max_length and compact.get("s"):
                compact["s"].pop()
                text = json.dumps(
                    compact, ensure_ascii=False, separators=(",", ":")
                )
        return text


class MemoryPersistenceFacade:
    """
    记忆持久化统一入口（Facade 模式）。

    委托到 LongTermMemory、MemoryRetrievalEngine、SkillAggregator（T4a）。
    所有方法均为 async，支持在 Agent 策略中直接调用。
    """

    def __init__(self, db_session_factory=None):
        self._session_factory = db_session_factory or get_db_session
        self._long_term = LongTermMemory(self._session_factory)
        from app.services.skill_aggregator import SkillAggregator
        from app.services.math_skill_dag import MathSkillDAG
        self._skill_aggregator = SkillAggregator(self._session_factory)
        self._skill_aggregator._skill_dag = MathSkillDAG()
        self._difficulty_estimator = None
        self._event_buffer = EnhancedEventBuffer()
        logger.info("MemoryPersistenceFacade 初始化完成（含 SkillAggregator + EventBuffer）")

    LEARNING_RECORD_FIELDS = {
    "user_id", "question_id", "event_type", "question_content",
    "category", "sub_categories", "difficulty", "user_answer",
    "correct_answer", "is_correct", "time_spent", "hint_count",
    "tools_used", "error_category", "error_reason",
    "correction_suggestion", "metadata_", "created_at",
}

    async def record_event(
        self, user_id: str, event_data: Dict[str, Any]
    ) -> bool:
        existing_uid = event_data.get("user_id")
        if existing_uid and existing_uid != "anonymous" and existing_uid.strip():
            pass
        else:
            event_data["user_id"] = user_id

        extra_fields = {}
        for key in list(event_data.keys()):
            if key not in self.LEARNING_RECORD_FIELDS:
                extra_fields[key] = event_data.pop(key)

        if extra_fields:
            existing_meta = event_data.get("metadata_", {}) or {}
            existing_meta.update(extra_fields)
            event_data["metadata_"] = existing_meta

        return await self._long_term.record_learning_event(event_data)

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        session_id: str = "default",
        limit: int = 10,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        short_term = ShortTermMemory()
        engine = MemoryRetrievalEngine(
            short_term_memory=short_term,
            long_term_memory=self._long_term,
        )
        results = await engine.retrieve(
            query=query, user_id=user_id, top_k=limit, min_score=min_score
        )
        return [
            {
                "id": r.memory.id,
                "type": r.memory.memory_type,
                "content": r.memory.content,
                "relevance": r.score,
                "source": r.source,
                "explanation": r.explanation,
            }
            for r in results
        ]

    async def get_profile(self, user_id: str) -> UserProfile:
        base = await self._long_term.get_user_profile(user_id)

        profile = UserProfile(
            total_questions=base.get("total_questions", 0),
            correct_rate=base.get("correct_rate", 0.0),
            avg_time_per_question=base.get("avg_time_per_question", 0.0),
            weak_points=base.get("weak_points", []),
            strong_points=base.get("strong_points", []),
            recommended_difficulty=base.get("recommended_difficulty", 3),
            recent_activity=base.get("recent_activity", []),
        )

        if self._skill_aggregator:
            profile.skills = await self._skill_aggregator.get_all_skills(
                user_id
            )
            profile.error_patterns = (
                await self._skill_aggregator.get_error_patterns(user_id)
            )
            profile.cognitive_style = (
                await self._skill_aggregator.get_cognitive_style(user_id)
            )

        return profile

    async def buffer_event(
        self, user_id: str, event_data: Dict[str, Any]
    ) -> bool:
        from app.services.event_buffer import BufferedEvent

        event = BufferedEvent(
            user_id=user_id,
            event_type=event_data.get("event_type", "unknown"),
            question_content=event_data.get("question_content", ""),
            category=event_data.get("category", ""),
            data=event_data,
        )
        return await self._event_buffer.add(event)

    async def flush_buffer(self) -> int:
        return await self._event_buffer.force_flush()

    INTENT_PERSISTENCE_MAP = {
        "problem_solving": {
            "persist": True, "ttl_days": 90,
            "record_detail": "full",
        },
        "concept_inquiry": {
            "persist": True, "ttl_days": 90,
            "record_detail": "summary",
        },
        "error_analysis": {
            "persist": True, "ttl_days": 180,
            "record_detail": "full",
        },
        "exam_practice": {
            "persist": True, "ttl_days": 180,
            "record_detail": "aggregated",
        },
        "casual_chat": {
            "persist": False, "ttl_days": 0,
            "record_detail": "none",
        },
    }

    def should_persist(self, intent_type: str) -> bool:
        config = self.INTENT_PERSISTENCE_MAP.get(intent_type, {})
        return config.get("persist", True)

    def get_persistence_config(
        self, intent_type: str
    ) -> Dict[str, Any]:
        return self.INTENT_PERSISTENCE_MAP.get(
            intent_type,
            {"persist": True, "ttl_days": 90, "record_detail": "full"},
        )