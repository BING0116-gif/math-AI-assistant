from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.data.database import get_db_session

logger = logging.getLogger(__name__)

SKILL_THRESHOLDS = {
    "novice": (0.00, 0.30),
    "learning": (0.30, 0.60),
    "proficient": (0.60, 0.85),
    "mastered": (0.85, 1.00),
}


class SkillAggregator:
    """
    从 learning_records 聚合计算用户的技能熟练度。

    核心算法: Elo-style 时间加权评分
    mastery = Σ(time_weight × diff_weight × result) / Σ(time_weight × diff_weight)
    """

    def __init__(self, db_session_factory=None):
        self._session_factory = db_session_factory or get_db_session
        self._skill_dag = None

    async def get_all_skills(
        self, user_id: str, max_skills: int = 50
    ) -> List[Dict[str, Any]]:
        # UserKnowledgeState 是学习画像的事实源。UserSkill 仅保留为旧调用方
        # 的兼容投影，运行时读取不能因投影延迟而返回陈旧画像。
        return await self._compute_skills(user_id, max_skills)

    async def recalculate_skills(
        self, user_id: str, skill_codes: Optional[List[str]] = None
    ) -> int:
        """Compatibility command: canonical states are already materialized.

        Kept as an API-level no-op/query during rollout so old callers do not
        break after the redundant user_skills table is retired.
        """
        skills = await self._compute_skills(user_id)
        if skill_codes:
            skills = [s for s in skills if s["skill_code"] in skill_codes]
        return len(skills)

    async def get_error_patterns(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import select
        from app.data.models import LearningRecord

        async with self._session_factory() as db:
            result = await db.execute(
                select(
                    LearningRecord.error_reason,
                    LearningRecord.category,
                ).where(
                    LearningRecord.user_id == user_id,
                    LearningRecord.is_correct.is_(False),
                    LearningRecord.error_reason.isnot(None),
                    LearningRecord.error_reason != "",
                )
            )
            rows = result.fetchall()

        # 应用层聚合（替代 GROUP_CONCAT，兼容 PostgreSQL / SQLite）
        agg: Dict[str, Dict[str, Any]] = {}
        for reason, category in rows:
            entry = agg.setdefault(reason, {"freq": 0, "categories": set()})
            entry["freq"] += 1
            if category:
                entry["categories"].add(category)

        candidates = [
            (reason, entry["freq"], entry["categories"])
            for reason, entry in agg.items()
            if len(entry["categories"]) >= 2
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        candidates = candidates[:10]

        total_errors = sum(freq for _, freq, _ in candidates) or 1
        return [
            {
                "pattern": reason,
                "frequency": round(freq / total_errors, 2),
                "affected_skills": sorted(categories),
            }
            for reason, freq, categories in candidates
        ]

    async def get_cognitive_style(
        self, user_id: str
    ) -> Dict[str, Any]:
        from sqlalchemy import text

        async with self._session_factory() as db:
            result = await db.execute(
                text(
                    "SELECT AVG(time_spent), COUNT(*) "
                    "FROM learning_records "
                    "WHERE user_id = :uid AND time_spent IS NOT NULL"
                ),
                {"uid": user_id},
            )
            row = result.fetchone()
            avg_time, count = row[0], row[1]

            if not count or count < 10:
                return {}

            return {
                "avg_time_per_question": round(avg_time or 0, 1),
                "total_analyzed": count,
                "style_hint": (
                    "快速型"
                    if avg_time and avg_time < 60
                    else "深思型"
                    if avg_time and avg_time > 180
                    else "标准型"
                ),
            }

    async def get_next_unlockable(self, user_id: str) -> List[Dict]:
        if not self._skill_dag:
            return []
        skills = await self.get_all_skills(user_id)
        mastered_ids = {
            s["skill_code"] for s in skills if s["status"] == "mastered"
        }
        learning_ids = {
            s["skill_code"] for s in skills if s["status"] != "mastered"
        }
        return self._skill_dag.get_next_unlockable(
            mastered_ids, learning_ids
        )

    async def get_prerequisite_check(
        self, user_id: str, skill_code: str
    ) -> Dict[str, Any]:
        if not self._skill_dag:
            return {"can_learn": True, "missing_prerequisites": []}
        skills = await self.get_all_skills(user_id)
        mastered_ids = {
            s["skill_code"] for s in skills if s["status"] == "mastered"
        }
        can = self._skill_dag.can_learn(skill_code, mastered_ids)
        missing = [
            p
            for p in self._skill_dag.get_prerequisites(skill_code)
            if p not in mastered_ids
        ]
        return {"can_learn": can, "missing_prerequisites": missing}

    async def _compute_skills(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import select
        from app.data.models import KnowledgePoint, UserKnowledgeState

        async with self._session_factory() as db:
            states = list((await db.execute(
                select(UserKnowledgeState)
                .where(UserKnowledgeState.user_id == user_id)
                .order_by(UserKnowledgeState.mastery.desc(), UserKnowledgeState.knowledge_point_code)
                .limit(limit)
            )).scalars())
            codes = [state.knowledge_point_code for state in states]
            points = list((await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.code.in_(codes or ["__none__"]))
            )).scalars())
            names = {point.code: point.name for point in points}
            skills = []
            for state in states:
                history = state.evolution_history or []
                streak = 0
                for event in reversed(history):
                    if not event.get("correct"):
                        break
                    streak += 1
                best = current = 0
                for event in history:
                    current = current + 1 if event.get("correct") else 0
                    best = max(best, current)
                status = self._determine_status(state.mastery)
                if status == "mastered":
                    kinds = {event.get("kind") for event in history if event.get("correct")}
                    if state.confidence < 0.7 or not {"variant", "spaced_review"}.issubset(kinds):
                        status = "proficient"
                skills.append({
                    "skill_code": state.knowledge_point_code,
                    "display_name": names.get(state.knowledge_point_code, state.knowledge_point_code),
                    "category_path": state.knowledge_point_code,
                    "mastery_level": state.mastery,
                    "memory_strength": state.memory_strength,
                    "confidence": state.confidence,
                    "status": status,
                    "total_attempts": state.attempts_count,
                    "correct_count": state.correct_count,
                    "recent_streak": streak, "best_streak": best,
                    "first_seen": history[0].get("at") if history else None,
                    "last_practiced": state.last_practiced_at.isoformat() if state.last_practiced_at else None,
                    "mastered_at": history[-1].get("at") if history and status == "mastered" else None,
                    "evolution_history": history,
                })
            return skills

    def _calculate_mastery(
        self,
        records: List[Tuple],
        now: datetime,
    ) -> Tuple[float, str, int, int, List[Dict]]:
        weighted_score = 0.0
        total_weight = 0.0
        current_streak = 0
        best_streak = 0
        history_points = []

        for i, (is_correct, difficulty, spent, created) in enumerate(
            reversed(records)
        ):
            created_dt = None
            if created:
                if isinstance(created, str):
                    try:
                        created_dt = datetime.fromisoformat(created)
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass
                elif hasattr(created, 'tzinfo'):
                    created_dt = created
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)

            if created_dt:
                days_ago = (now - created_dt).days
            else:
                days_ago = 0

            time_weight = 0.5 ** (days_ago / 14)
            diff_weight = 0.5 + ((difficulty or 3) / 10)
            result_score = 1.0 if is_correct else 0.0

            combined = time_weight * diff_weight * result_score
            weighted_score += combined
            total_weight += time_weight * diff_weight

            if is_correct:
                current_streak += 1
                best_streak = max(best_streak, current_streak)
            else:
                current_streak = 0

            if (i + 1) % 5 == 0 or i == len(records) - 1:
                mastery = (
                    weighted_score / total_weight
                    if total_weight > 0
                    else 0.0
                )
                history_points.append(
                    {
                        "date": created_dt.isoformat() if created_dt else (str(created) if created else ""),
                        "mastery": round(mastery, 3),
                        "attempts": i + 1,
                    }
                )

        mastery = (
            weighted_score / total_weight if total_weight > 0 else 0.0
        )
        status = self._determine_status(mastery)
        return mastery, status, current_streak, best_streak, history_points

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """将 ISO 字符串 / datetime 解析为 aware datetime。

        SQLite / PostgreSQL 的 DateTime 列均要求 Python datetime 对象，
        不能直接写入 ISO 字符串（跨方言兼容修复）。
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _determine_status(mastery: float) -> str:
        for status, (lo, hi) in SKILL_THRESHOLDS.items():
            if lo <= mastery < hi:
                return status
        return "mastered"

    @staticmethod
    def _derive_skill_code(category: str, sub_category: str) -> str:
        import re as _re
        raw = f"{category}_{sub_category}".lower()
        return _re.sub(r"[^a-z0-9_]", "_", raw)[:50]
