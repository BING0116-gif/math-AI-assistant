from __future__ import annotations

import asyncio
import json
import logging
import time
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

# ── P2：自动技能重计算触发条件 ──
RECALC_TRIGGER = {
    "event_count": 3,          # 每 N 条事件触发一次重计算（降低门槛：聊天场景下更快反馈）
    "min_interval": 30,        # 最小重计算间隔（秒）（从60降到30）
    "batch_threshold": 50,     # 缓冲区满阈值触发
    "flush_callback": True,    # 是否注册 EventBuffer 刷新回调
}
"""技能重计算自动触发配置。

- event_count: record_event 每写入 N 条事件后触发一次 recalculate_skills
- min_interval: 避免高频率重复重计算的最小间隔（秒）
- batch_threshold: 缓冲区批量写入 N 条后触发
- flush_callback: 注册为 EventBuffer 的 on_flush 回调
"""

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

        # ── P1：DifficultyEstimator 集成 ──
        from app.services.difficulty_estimator import DifficultyEstimator
        self._difficulty_estimator = DifficultyEstimator(
            skill_aggregator=self._skill_aggregator,
            db_session_factory=self._session_factory,
        )

        # ── P2：事件缓冲 + 自动重计算 ──
        self._last_recalc_time: Dict[str, float] = {}
        self._event_buffer = EnhancedEventBuffer()
        self._event_count_since_recalc: Dict[str, int] = {}
        if RECALC_TRIGGER["flush_callback"]:
            self._event_buffer.on_flush(self._on_buffer_flush)

        # ─ P0-02：批量写入队列 + 失败重试 ──
        self._batch_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._batch_worker_task: Optional[asyncio.Task] = None
        self._batch_size = 10  # 每10条刷新
        self._flush_interval = 5.0  # 每5秒刷新
        # 不在 __init__ 中启动 worker（可能无运行中的事件循环），改为懒加载

        logger.info(
            "MemoryPersistenceFacade 初始化完成 "
            "(含 SkillAggregator + DifficultyEstimator + EventBuffer + BatchWriter)"
        )

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

        # [P0-02] 懒启动批量写入worker（首次调用时才启动，确保有事件循环）
        self._ensure_batch_worker_started()

        # [P0-02] 使用批量写入队列（非阻塞，加入队列即返回）
        try:
            await asyncio.wait_for(
                self._batch_queue.put(event_data), timeout=1.0
            )
            # ── P2：记录加入队列后，自动触发技能重计算检查 ──
            if user_id:
                asyncio.ensure_future(self._maybe_trigger_recalc(user_id))
            return True
        except asyncio.TimeoutError:
            logger.error("批量队列已满，事件丢弃")
            return False

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

        # ── P1：使用 DifficultyEstimator 动态计算推荐难度 ──
        if self._difficulty_estimator:
            try:
                dynamic_diff = await self._difficulty_estimator.estimate_for_profile(
                    user_id=user_id, profile=profile
                )
                profile.recommended_difficulty = dynamic_diff
                logger.debug(
                    f"动态难度已更新: {base.get('recommended_difficulty', 3)} → {dynamic_diff}"
                )
            except Exception as e:
                logger.warning(f"动态难度计算失败（保留基础值）: {e}")

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

    # ── P1: 公共难度估算接口 ──

    async def estimate_difficulty(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        context: str = "practice",
    ) -> int:
        """
        估算指定知识点的推荐难度（公共接口）。

        Args:
            user_id: 用户 ID
            category: 知识点分类
            sub_category: 子分类
            context: 上下文模式（practice/exam/review/error_correction/challenge）

        Returns:
            int: 推荐难度 1-5
        """
        if not self._difficulty_estimator:
            return 3
        return await self._difficulty_estimator.estimate(
            user_id=user_id,
            category=category,
            sub_category=sub_category,
            context=context,
        )

    # ── P0-02: 批量写入队列 + 失败重试 ──

    def _ensure_batch_worker_started(self) -> None:
        """懒启动批量写入worker（首次调用时启动，确保有事件循环）。"""
        if self._batch_worker_task is None or self._batch_worker_task.done():
            try:
                self._batch_worker_task = asyncio.create_task(self._batch_worker())
                logger.debug("批量写入worker已懒启动")
            except RuntimeError:
                # 无运行中的事件循环，跳过（非关键路径）
                logger.debug("批量写入worker跳过启动（无事件循环）")

    def _start_batch_worker(self) -> None:
        """启动后台批量写入worker（供显式调用）。"""
        self._ensure_batch_worker_started()

    async def _batch_worker(self) -> None:
        """后台worker：批量写入，每10条或5秒刷新一次。"""
        batch = []
        last_flush = time.time()
        while True:
            try:
                try:
                    event = await asyncio.wait_for(
                        self._batch_queue.get(), timeout=1.0
                    )
                    batch.append(event)
                except asyncio.TimeoutError:
                    pass

                now = time.time()
                should_flush = (
                    len(batch) >= self._batch_size
                    or (batch and now - last_flush >= self._flush_interval)
                )
                if should_flush and batch:
                    await self._flush_batch(batch)
                    batch = []
                    last_flush = now
            except Exception as e:
                logger.error(f"批量写入worker异常: {e}")
                await asyncio.sleep(1.0)

    async def _flush_batch(self, batch: List[Dict]) -> None:
        """刷新批量数据到数据库。"""
        from app.data.models import LearningRecord

        try:
            async with self._session_factory() as db:
                for data in batch:
                    record = LearningRecord(**{
                        k: v for k, v in data.items()
                        if k in LearningRecord.__table__.columns
                    })
                    db.add(record)
                await db.commit()
                logger.info(f"批量写入成功: {len(batch)}条")
        except Exception as e:
            logger.error(f"批量写入失败: {e}")
            await self._retry_flush(batch)

    async def _retry_flush(self, batch: List[Dict], max_retries: int = 3) -> None:
        """指数退避重试。"""
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
                await self._flush_batch(batch)
                logger.info(f"重试成功: attempt={attempt+1}")
                return
            except Exception:
                logger.warning(f"重试失败: attempt={attempt+1}")
        logger.error(f"批量写入最终失败（重试{max_retries}次），共{len(batch)}条事件丢弃")

    # ── P2: 自动技能重计算机制 ──

    async def trigger_skill_recalculation(
        self,
        user_id: str,
        skill_codes: Optional[List[str]] = None,
    ) -> int:
        """
        显式触发技能重计算（供外部调用）。

        Args:
            user_id: 用户 ID
            skill_codes: 指定技能代码列表，None 表示重算全部

        Returns:
            int: 更新的 skill 数量
        """
        if not self._skill_aggregator:
            logger.warning("SkillAggregator 未初始化，跳过重计算")
            return 0

        try:
            count = await self._skill_aggregator.recalculate_skills(
                user_id=user_id, skill_codes=skill_codes
            )
            self._last_recalc_time[user_id] = time.time()
            self._event_count_since_recalc[user_id] = 0
            logger.info(
                f"技能重计算完成: user={user_id} "
                f"skills_updated={count} "
                f"codes={skill_codes or 'all'}"
            )
            return count
        except Exception as e:
            logger.error(f"技能重计算失败: user={user_id} error={e}")
            return 0

    async def get_recalc_status(self, user_id: str) -> Dict[str, Any]:
        """获取重计算状态信息。"""
        last_time = self._last_recalc_time.get(user_id, 0.0)
        last_dt = (
            datetime.fromtimestamp(last_time, tz=timezone.utc).isoformat()
            if last_time > 0
            else None
        )
        return {
            "user_id": user_id,
            "last_recalc_at": last_dt or "never",
            "events_since_recalc": self._event_count_since_recalc.get(user_id, 0),
            "trigger_config": dict(RECALC_TRIGGER),
        }

    async def _maybe_trigger_recalc(self, user_id: str) -> bool:
        """
        检查并触发自动重计算（内部调用）。

        触发条件（任一满足）：
        1. 距上次重计算记录的事件数 >= event_count
        2. 距上次重计算时间间隔 >= min_interval（但仅在 event_count 达标时）
        3. 首次重计算（尚无记录）

        Returns:
            bool: 是否触发了重计算
        """
        # 检查间隔保护
        now = time.time()
        last = self._last_recalc_time.get(user_id, 0.0)
        if last > 0 and (now - last) < RECALC_TRIGGER["min_interval"]:
            return False  # 间隔太短，跳过

        # 更新事件计数
        count = self._event_count_since_recalc.get(user_id, 0) + 1
        self._event_count_since_recalc[user_id] = count

        # 触发条件：事件数达标
        if count < RECALC_TRIGGER["event_count"]:
            return False

        # 执行异步重计算（非阻塞）
        asyncio.ensure_future(self.trigger_skill_recalculation(user_id))
        return True

    async def _on_buffer_flush(self, events: List) -> None:
        """
        EventBuffer 刷新回调。
        当缓冲区批量写入时，触发技能重计算。

        Args:
            events: 被刷新的缓冲事件列表
        """
        if not events:
            return

        if len(events) < RECALC_TRIGGER["batch_threshold"]:
            return

        # 提取唯一的 user_id
        user_ids = set(e.user_id for e in events if e.user_id)
        for uid in user_ids:
            asyncio.ensure_future(self.trigger_skill_recalculation(uid))

        logger.info(
            f"缓冲区批量刷新回调触发重计算: "
            f"events={len(events)} users={len(user_ids)}"
        )

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