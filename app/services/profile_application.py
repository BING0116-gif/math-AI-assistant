"""
画像应用层 — 统一 ProfileSnapshot 定义与持久化。

本模块仅提供：
1. ProfileSnapshot dataclass（唯一应用层快照）
2. ProfileSnapshotRepository（ORM 读写 user_profiles）

不包含画像生成逻辑；生成逻辑在 MemoryPersistenceFacade 中编排。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete

from app.data.models import UserProfile

logger = logging.getLogger(__name__)


@dataclass
class ProfileSnapshot:
    """统一画像快照 — 唯一应用层画像入口。

    所有消费者（Profile API、Agent、Recommendation、Admin Dashboard）
    均通过此对象获取画像数据。
    """

    # ── 标识 ──
    user_id: str
    version: int = 1
    generated_at: str = ""

    # ── 统计摘要 ──
    total_questions: int = 0
    correct_rate: float = 0.0
    avg_time_per_question: float = 0.0
    recommended_difficulty: int = 3

    # ── 能力 ──
    weak_points: List[Dict[str, Any]] = field(default_factory=list)
    strong_points: List[str] = field(default_factory=list)
    skills: List[Dict[str, Any]] = field(default_factory=list)

    # ── 行为分析 ──
    behavior: Dict[str, Any] = field(default_factory=dict)
    recent_activity: List[Dict[str, Any]] = field(default_factory=list)

    # ── 错误分析 ──
    error_patterns: Dict[str, Any] = field(default_factory=dict)
    error_pattern_list: List[Dict[str, Any]] = field(default_factory=list)

    # ── 进度趋势 ──
    progress_trends: Dict[str, Any] = field(default_factory=dict)

    # ── 偏好 ──
    preferences: Dict[str, Any] = field(default_factory=dict)

    # ── 认知风格（技能级） ──
    cognitive_style: Dict[str, Any] = field(default_factory=dict)

    # ── 推荐建议 ──
    recommendations: List[Dict[str, Any]] = field(default_factory=list)

    # ── 摘要文本（用于 Prompt 注入 / 管理端展示） ──
    summary_text: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    # ── 序列化 ──

    @staticmethod
    def _sanitize(obj: Any) -> Any:
        """递归清洗：Decimal → float，保证全量 JSON 可序列化（PostgreSQL 返回 Decimal）。"""
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: ProfileSnapshot._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ProfileSnapshot._sanitize(v) for v in obj]
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """返回完整可 JSON 序列化的 dict（用于持久化 user_profiles）。"""
        return ProfileSnapshot._sanitize({
            "user_id": self.user_id,
            "version": self.version,
            "generated_at": self.generated_at,
            "total_questions": self.total_questions,
            "correct_rate": self.correct_rate,
            "avg_time_per_question": self.avg_time_per_question,
            "recommended_difficulty": self.recommended_difficulty,
            "weak_points": self.weak_points,
            "strong_points": self.strong_points,
            "skills": self.skills,
            "behavior": self.behavior,
            "recent_activity": self.recent_activity,
            "error_patterns": self.error_patterns,
            "error_pattern_list": self.error_pattern_list,
            "progress_trends": self.progress_trends,
            "preferences": self.preferences,
            "cognitive_style": self.cognitive_style,
            "recommendations": self.recommendations,
            "summary_text": self.summary_text,
        })

    @classmethod
    def from_dict(cls, user_id: str, data: Dict[str, Any]) -> ProfileSnapshot:
        """从 dict 反序列化（用于从 user_profiles 恢复）。"""
        return cls(
            user_id=user_id,
            version=data.get("version", 1),
            generated_at=data.get("generated_at", ""),
            total_questions=data.get("total_questions", 0),
            correct_rate=data.get("correct_rate", 0.0),
            avg_time_per_question=data.get("avg_time_per_question", 0.0),
            recommended_difficulty=data.get("recommended_difficulty", 3),
            weak_points=data.get("weak_points", []),
            strong_points=data.get("strong_points", []),
            skills=data.get("skills", []),
            behavior=data.get("behavior", {}),
            recent_activity=data.get("recent_activity", []),
            error_patterns=data.get("error_patterns", {}),
            error_pattern_list=data.get("error_pattern_list", []),
            progress_trends=data.get("progress_trends", {}),
            preferences=data.get("preferences", {}),
            cognitive_style=data.get("cognitive_style", {}),
            recommendations=data.get("recommendations", []),
            summary_text=data.get("summary_text", ""),
        )

    def to_compact_json(self, max_length: int = 800) -> str:
        """紧凑 JSON 格式（用于 Agent Prompt 注入）。"""
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

    def get_learning_level(self) -> str:
        """根据 correct_rate 推断学习等级。"""
        cr = self.correct_rate
        if cr > 0.85:
            return "expert"
        elif cr > 0.7:
            return "advanced"
        elif cr > 0.5:
            return "intermediate"
        elif cr > 0.3:
            return "elementary"
        return "beginner"


class ProfileSnapshotRepository:
    """user_profiles 表的 ORM 读写封装。

    使用读-改-写模式（非裸 SQL upsert），兼容 PostgreSQL / SQLite / MySQL。
    写入频率低（仅 refresh 时），单次读-改-写足够。
    """

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get(self, user_id: str) -> Optional[ProfileSnapshot]:
        """从 user_profiles 表读取快照。"""
        try:
            async with self._session_factory() as db:
                result = await db.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                now_ts = int(datetime.now(timezone.utc).timestamp())
                if row.expire_at is not None and row.expire_at <= now_ts:
                    return None
                data = json.loads(row.full_profile_json)
                snapshot = ProfileSnapshot.from_dict(user_id, data)
                snapshot.version = row.version
                return snapshot
        except Exception as e:
            logger.error(f"[ProfileSnapshotRepo] 读取失败: user={user_id} error={e}")
            return None

    async def upsert(self, snapshot: ProfileSnapshot) -> bool:
        """保存快照到 user_profiles 表（读-改-写模式）。"""
        try:
            full_json = json.dumps(snapshot.to_dict(), ensure_ascii=False)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            async with self._session_factory() as db:
                result = await db.execute(
                    select(UserProfile).where(UserProfile.user_id == snapshot.user_id)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.summary_text = snapshot.summary_text
                    existing.full_profile_json = full_json
                    existing.version = snapshot.version
                    existing.updated_at = now_ts
                    existing.expire_at = None
                else:
                    db.add(UserProfile(
                        user_id=snapshot.user_id,
                        summary_text=snapshot.summary_text,
                        full_profile_json=full_json,
                        version=snapshot.version,
                        updated_at=now_ts,
                        expire_at=None,
                    ))
                await db.commit()
                logger.debug(f"[ProfileSnapshotRepo] 保存成功: user={snapshot.user_id}")
                return True
        except Exception as e:
            logger.error(f"[ProfileSnapshotRepo] 保存失败: user={snapshot.user_id} error={e}")
            return False

    async def invalidate(self, user_id: str) -> bool:
        """标记持久化快照过期；事实层数据不受影响。"""
        try:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            async with self._session_factory() as db:
                result = await db.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return False
                row.expire_at = now_ts
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"[ProfileSnapshotRepo] 失效失败: user={user_id} error={e}")
            return False

    async def delete(self, user_id: str) -> bool:
        """删除用户快照（用于测试快照可重建性）。"""
        try:
            async with self._session_factory() as db:
                result = await db.execute(
                    delete(UserProfile).where(UserProfile.user_id == user_id)
                )
                await db.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[ProfileSnapshotRepo] 删除失败: user={user_id} error={e}")
            return False
