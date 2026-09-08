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
from app.services.profile_application import (
    ProfileSnapshot,
    ProfileSnapshotRepository,
)
from app.services.cache import get_cache_manager
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

# ── 画像快照缓存 ──
PROFILE_SNAPSHOT_CACHE_PREFIX = "user:profile:snapshot:"
PROFILE_SNAPSHOT_CACHE_TTL = 300  # 秒

@dataclass
class UserProfile:
    """用户画像（扩展版），包含原有统计字段 + Skill 字段 + 错误模式"""

    user_id: str = ""
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
        self,
        user_id: str,
        event_data: Dict[str, Any],
        *,
        event_id: Optional[str] = None,
    ) -> bool:
        """记录一条学习事件（异步批量写入）。

        Args:
            user_id: 用户 ID
            event_data: 事件数据（写入 learning_records 的字段）
            event_id: 稳定事件 ID（幂等）。相同 event_id 只写入一次事实；
                      由调用方生成稳定 ID，禁止用随机值冒充。
                      未提供时保持兼容（无去重），并记录弃用日志。

        Returns:
            bool: 是否已成功加入写入队列。
        """
        if event_id is None:
            event_id = event_data.pop("event_id", None) or (
                (event_data.get("metadata_") or {}).get("event_id")
            )
            if event_id is None:
                logger.warning(
                    "record_event 未提供 event_id，无法保证幂等（deprecated）: "
                    f"user={user_id}, event_type={event_data.get('event_type')}"
                )

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

        # 事件 ID 仅用于写入期幂等去重（LearningRecord 无 event_id 列，
        # 批量写入时会被过滤掉，不会落库）
        if event_id:
            event_data["event_id"] = event_id

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
        """兼容入口：返回旧版 UserProfile（内部转发到统一画像快照）。

        保留供 Agent / Recommendation 等旧调用方使用；新代码应使用
        get_profile_snapshot() 获取统一快照。
        """
        snapshot = await self.get_profile_snapshot(user_id)
        return self._snapshot_to_legacy(snapshot)

    def _snapshot_to_legacy(self, snapshot: ProfileSnapshot) -> UserProfile:
        """将统一快照转换为旧版 UserProfile dataclass（兼容入口）。"""
        return UserProfile(
            user_id=snapshot.user_id,
            total_questions=snapshot.total_questions,
            correct_rate=snapshot.correct_rate,
            avg_time_per_question=snapshot.avg_time_per_question,
            weak_points=snapshot.weak_points,
            strong_points=snapshot.strong_points,
            recommended_difficulty=snapshot.recommended_difficulty,
            recent_activity=snapshot.recent_activity,
            skills=snapshot.skills,
            error_patterns=snapshot.error_pattern_list,
            cognitive_style=snapshot.cognitive_style,
        )

    # ── 唯一画像应用入口：ProfileSnapshot ──

    async def get_profile_snapshot(
        self,
        user_id: str,
        *,
        force_refresh: bool = False,
    ) -> ProfileSnapshot:
        """获取统一画像快照（唯一应用层画像入口）。

        读取优先级（fallback 链）：
        1. 缓存（cache.py L1 + Redis L2，key 含 user_id）
        2. 持久化快照（user_profiles，materialized snapshot，可重建）
        3. 从事实层重建（learning_records / user_skills / memories）+ 持久化 + 缓存

        任何一层失败都会降级到下一层；Redis down 不影响正确性。
        """
        cache_key = self._profile_snapshot_cache_key(user_id)

        if not force_refresh:
            cache = get_cache_manager()
            cached = await cache.get(cache_key)
            if cached is not None:
                try:
                    return ProfileSnapshot.from_dict(user_id, cached)
                except Exception as e:
                    logger.warning(f"画像快照缓存反序列化失败，回源重建: {e}")

            # 尝试从持久化快照读取（user_profiles）
            repo = ProfileSnapshotRepository(self._session_factory)
            persisted = await repo.get(user_id)
            if persisted is not None:
                await cache.set(cache_key, persisted.to_dict(), ttl=PROFILE_SNAPSHOT_CACHE_TTL)
                return persisted

        # 从事实层重建
        return await self.refresh_profile_snapshot(user_id)

    async def refresh_profile_snapshot(self, user_id: str) -> ProfileSnapshot:
        """从事实层完整重建画像快照并持久化、刷新缓存。

        同一批事实下重复调用结果一致（幂等）。
        """
        snapshot = await self._build_profile_snapshot(user_id)

        # 持久化到 user_profiles（materialized snapshot，可重建）
        repo = ProfileSnapshotRepository(self._session_factory)
        await repo.upsert(snapshot)

        # 写缓存
        cache = get_cache_manager()
        await cache.set(
            self._profile_snapshot_cache_key(user_id),
            snapshot.to_dict(),
            ttl=PROFILE_SNAPSHOT_CACHE_TTL,
        )

        return snapshot

    async def invalidate_profile_snapshot(self, user_id: str) -> None:
        """使缓存和持久化物化快照同时失效。

        user_profiles 仍被保留用于审计，但下一次读取必须从事实层重建，
        避免缓存清除后重新读到陈旧的持久化快照。
        """
        try:
            cache = get_cache_manager()
            await cache.delete(self._profile_snapshot_cache_key(user_id))
        except Exception as e:
            logger.warning(f"画像快照缓存失效失败（可忽略）: user={user_id} error={e}")
        repo = ProfileSnapshotRepository(self._session_factory)
        await repo.invalidate(user_id)

    def _profile_snapshot_cache_key(self, user_id: str) -> str:
        return f"{PROFILE_SNAPSHOT_CACHE_PREFIX}{user_id}"

    async def _build_profile_snapshot(self, user_id: str) -> ProfileSnapshot:
        """画像快照统一生成逻辑（内部计算组件）。

        复用：
        - LongTermMemory.get_user_profile（事实统计）
        - SkillAggregator（技能聚合，唯一实现）
        - DifficultyEstimator（难度估算）
        - UserProfileAnalyzer（行为/错误/进度/偏好分析，作为内部组件）
        """
        base = await self._long_term.get_user_profile(user_id)

        # 技能相关（来自 SkillAggregator，唯一实现）
        skills: List[Dict[str, Any]] = []
        error_pattern_list: List[Dict[str, Any]] = []
        cognitive_style: Dict[str, Any] = {}
        if self._skill_aggregator:
            skills = await self._skill_aggregator.get_all_skills(user_id)
            error_pattern_list = (
                await self._skill_aggregator.get_error_patterns(user_id)
            )
            cognitive_style = (
                await self._skill_aggregator.get_cognitive_style(user_id)
            )

        # 推荐难度（DifficultyEstimator 动态计算）
        recommended_difficulty = base.get("recommended_difficulty", 3)
        if self._difficulty_estimator:
            try:
                dynamic_diff = await self._difficulty_estimator.estimate_for_profile(
                    user_id=user_id,
                    profile=self._to_legacy_profile(
                        user_id, base, skills, error_pattern_list, cognitive_style
                    ),
                )
                recommended_difficulty = dynamic_diff
            except Exception as e:
                logger.warning(f"动态难度计算失败（保留基础值）: {e}")

        # 行为 / 错误 / 进度 / 偏好 / 推荐（UserProfileAnalyzer 作为内部组件）
        analyzer_data: Dict[str, Any] = {}
        try:
            from app.services.profile_analyzer import UserProfileAnalyzer

            analyzer = UserProfileAnalyzer(self._session_factory)
            analyzed = await analyzer.analyze(user_id)
            analyzer_data.update(analyzed)
        except Exception as e:
            logger.warning(f"画像深度分析失败（使用基础统计）: {e}")

        canonical_weak = [
            {
                "category": skill.get("display_name") or skill.get("skill_code", ""),
                "mastery": float(skill.get("mastery_level") or 0),
                "mastery_score": float(skill.get("mastery_level") or 0),
                "evidence_count": skill.get("evidence_count", 0),
                "confidence_level": skill.get("confidence_level", "insufficient"),
                "confidence": float(skill.get("confidence") or 0),
                "memory_strength": float(skill.get("memory_strength") or 0),
            }
            for skill in skills
            if skill.get("status") in {"novice", "learning"}
        ][:10]
        canonical_strong = [
            skill.get("display_name") or skill.get("skill_code", "")
            for skill in skills
            if skill.get("status") == "mastered"
        ][:10]

        snapshot = ProfileSnapshot(
            user_id=user_id,
            version=base.get("version", 1),
            total_questions=base.get("total_questions", 0),
            correct_rate=base.get("correct_rate", 0.0),
            avg_time_per_question=base.get("avg_time_per_question", 0.0),
            recommended_difficulty=recommended_difficulty,
            weak_points=canonical_weak or base.get("weak_points", []),
            strong_points=canonical_strong or base.get("strong_points", []),
            skills=skills,
            error_patterns=analyzer_data.get("error_patterns", {}),
            behavior=analyzer_data.get("behavior", {}),
            progress_trends=analyzer_data.get("progress_trends", {}),
            preferences=analyzer_data.get("preferences", {}),
            recommendations=analyzer_data.get("recommendations", []),
            recent_activity=base.get("recent_activity", []),
            cognitive_style=cognitive_style,
        )
        snapshot.error_pattern_list = error_pattern_list
        snapshot.summary_text = self._generate_profile_summary(snapshot)
        return snapshot

    def _to_legacy_profile(
        self,
        user_id: str,
        base: Dict[str, Any],
        skills: List[Dict[str, Any]],
        error_pattern_list: List[Dict[str, Any]],
        cognitive_style: Dict[str, Any],
    ) -> UserProfile:
        """将基础数据包装为旧版 UserProfile（供 DifficultyEstimator 兼容）。"""
        legacy = UserProfile(
            user_id=user_id,
            total_questions=base.get("total_questions", 0),
            correct_rate=base.get("correct_rate", 0.0),
            avg_time_per_question=base.get("avg_time_per_question", 0.0),
            weak_points=base.get("weak_points", []),
            strong_points=base.get("strong_points", []),
            recommended_difficulty=base.get("recommended_difficulty", 3),
            recent_activity=base.get("recent_activity", []),
            skills=skills,
            error_patterns=error_pattern_list,
            cognitive_style=cognitive_style,
        )
        return legacy

    @staticmethod
    def _generate_profile_summary(snapshot: ProfileSnapshot) -> str:
        """从快照生成摘要文本（用于 Prompt 注入 / 管理端展示）。"""
        parts = []
        weak_points = snapshot.weak_points
        if weak_points:
            weak_str = "、".join(
                w.get("category", "") for w in weak_points[:5] if w.get("category")
            )
            if weak_str:
                parts.append(f"薄弱知识点：{weak_str}")

        mastered = [
            s.get("display_name") or s.get("skill_code", "")
            for s in snapshot.skills
            if s.get("status") == "mastered"
        ]
        if mastered:
            parts.append(f"已掌握：{'、'.join(mastered[:3])}")

        ep = snapshot.error_patterns
        if isinstance(ep, dict):
            common = ep.get("common_error_reasons", []) or ep.get("common_errors", [])
            if common:
                first = common[0]
                reason = (
                    first.get("reason", "") if isinstance(first, dict) else str(first)
                )
                if reason:
                    parts.append(f"易犯错误：{reason[:40]}")

        prefs = snapshot.preferences
        if isinstance(prefs, dict) and prefs.get("difficulty_mode") == "fixed":
            parts.append("固定难度模式")

        return "；".join(parts) if parts else "该用户暂无详细画像数据。"

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
        """刷新批量数据到数据库。

        带 event_id 的事件做原子幂等去重：先 claim（EventIdempotency，
        event_id UNIQUE + 冲突即跳过），成功后才写事实 learning_records。
        claim 与事实写入处于同一事务（savepoint 回滚失败 claim）。
        """
        from app.data.models import LearningRecord, EventIdempotency
        from sqlalchemy.exc import IntegrityError

        try:
            async with self._session_factory() as db:
                inserted = 0
                async with db.begin():
                    for data in batch:
                        event_id = data.get("event_id")
                        if event_id:
                            try:
                                # 原子 claim：唯一键冲突 → 已处理，跳过
                                async with db.begin_nested():
                                    db.add(EventIdempotency(
                                        event_id=event_id,
                                        event_type=str(data.get("event_type", "learning_record"))[:64],
                                        processed_at=int(time.time()),
                                        status="processed",
                                    ))
                                    await db.flush()
                                db.add(LearningRecord(**{
                                    k: v for k, v in data.items()
                                    # 注意：必须按模型属性名过滤。metadata_ 列显式命名为
                                    # "metadata"，列 key 也随之变成 "metadata"，直接用
                                    # `k in columns`（按列名/列 key 匹配）会把 metadata_
                                    # 静默丢弃（T02 修复；event_id 不是模型属性，同样被过滤）。
                                    if hasattr(LearningRecord, k)
                                }))
                                inserted += 1
                            except IntegrityError:
                                logger.debug(f"事件已处理，跳过重复写入: event_id={event_id}")
                                continue
                        else:
                            db.add(LearningRecord(**{
                                k: v for k, v in data.items()
                                if hasattr(LearningRecord, k)
                            }))
                            inserted += 1
                logger.info(f"批量写入成功: {len(batch)}条队列, {inserted}条实际落库")
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
            # 技能状态变更 → 使画像快照缓存失效（下次读取重建）
            await self.invalidate_profile_snapshot(user_id)
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
