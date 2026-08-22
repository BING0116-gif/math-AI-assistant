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
        from sqlalchemy import select
        from app.data.models import UserSkill

        async with self._session_factory() as db:
            result = await db.execute(
                select(UserSkill)
                .where(UserSkill.user_id == user_id)
                .order_by(UserSkill.mastery_level.desc())
                .limit(max_skills)
            )
            skills = result.scalars().all()

            if skills:
                return [
                    {
                        "skill_code": s.skill_code,
                        "display_name": s.display_name,
                        "category_path": s.category_path,
                        "mastery_level": s.mastery_level,
                        "status": s.status,
                        "total_attempts": s.total_attempts,
                        "correct_count": s.correct_count,
                        "recent_streak": s.recent_streak,
                        "best_streak": s.best_streak,
                        "last_practiced": (
                            s.last_practiced_at.isoformat()
                            if s.last_practiced_at else None
                        ),
                        "first_seen": (
                            s.first_seen_at.isoformat()
                            if s.first_seen_at else None
                        ),
                        "mastered_at": (
                            s.mastered_at.isoformat()
                            if s.mastered_at else None
                        ),
                        "evolution_history": s.evolution_history or [],
                    }
                    for s in skills
                ]

            return await self._compute_skills(user_id, max_skills)

    async def recalculate_skills(
        self, user_id: str, skill_codes: Optional[List[str]] = None
    ) -> int:
        skills = await self._compute_skills(user_id)

        filtered = skills
        if skill_codes:
            filtered = [s for s in skills if s["skill_code"] in skill_codes]

        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.data.models import UserSkill

        async with self._session_factory() as db:
            dialect = db.bind.dialect.name if db.bind else "sqlite"
            for skill in filtered:
                values = {
                    "user_id": user_id,
                    "skill_code": skill["skill_code"],
                    "display_name": skill["display_name"],
                    "category_path": skill.get("category_path", ""),
                    "mastery_level": skill["mastery_level"],
                    "status": skill["status"],
                    "total_attempts": skill["total_attempts"],
                    "correct_count": skill["correct_count"],
                    "recent_streak": skill["recent_streak"],
                    "best_streak": skill["best_streak"],
                    "first_seen_at": self._parse_datetime(skill.get("first_seen")),
                    "last_practiced_at": self._parse_datetime(skill.get("last_practiced")),
                    "mastered_at": self._parse_datetime(skill.get("mastered_at")),
                    "evolution_history": skill.get("evolution_history", []),
                }

                if dialect == "postgresql":
                    stmt = pg_insert(UserSkill).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_id", "skill_code"],
                        set_={
                            "display_name": stmt.excluded.display_name,
                            "category_path": stmt.excluded.category_path,
                            "mastery_level": stmt.excluded.mastery_level,
                            "status": stmt.excluded.status,
                            "total_attempts": stmt.excluded.total_attempts,
                            "correct_count": stmt.excluded.correct_count,
                            "recent_streak": stmt.excluded.recent_streak,
                            "best_streak": stmt.excluded.best_streak,
                            "last_practiced_at": stmt.excluded.last_practiced_at,
                            "evolution_history": stmt.excluded.evolution_history,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await db.execute(stmt)
                else:
                    # SQLite / 其他方言：读-改-写（低频率写，非关键路径）
                    existing = await db.execute(
                        select(UserSkill).where(
                            UserSkill.user_id == user_id,
                            UserSkill.skill_code == skill["skill_code"],
                        )
                    )
                    row = existing.scalar_one_or_none()
                    if row is not None:
                        for k, v in values.items():
                            setattr(row, k, v)
                    else:
                        db.add(UserSkill(**values))
            await db.commit()
        return len(filtered)

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
        from sqlalchemy import text

        async with self._session_factory() as db:
            # 查询1: 有sub_categories的记录（精确匹配）
            result = await db.execute(
                text(
                    "SELECT DISTINCT sub_categories, category "
                    "FROM learning_records "
                    "WHERE user_id = :uid AND sub_categories IS NOT NULL "
                    "AND sub_categories != ''"
                ),
                {"uid": user_id},
            )
            precise_rows = result.fetchall()

            # 查询2: 只有category没有sub_category的记录（兜底，避免浪费数据）
            result2 = await db.execute(
                text(
                    "SELECT DISTINCT NULL as sub_categories, category "
                    "FROM learning_records "
                    "WHERE user_id = :uid AND (sub_categories IS NULL OR sub_categories = '')"
                    " AND category IS NOT NULL AND category != ''"
                    " AND category NOT IN ("
                    "   SELECT DISTINCT category FROM learning_records "
                    "   WHERE user_id = :uid AND sub_categories IS NOT NULL AND sub_categories != ''"
                    " )"
                ),
                {"uid": user_id},
            )
            fallback_rows = result2.fetchall()

            skill_rows = list(precise_rows) + list(fallback_rows)

            skills = []
            now = datetime.now(timezone.utc)

            for row in skill_rows:
                sub_cat = row[0]
                category = row[1]

                # 处理sub_category为空的情况（category级别兜底）
                if not sub_cat or str(sub_cat).strip() == '':
                    sub_cat_display = f"{category}(综合)"
                    skill_code = self._derive_skill_code(category, "general")
                    cat_path = category
                    # 查询时只按category匹配
                    query_sc = ""
                else:
                    sub_cat_display = sub_cat
                    skill_code = self._derive_skill_code(category, sub_cat)
                    cat_path = f"{category} > {sub_cat}"
                    query_sc = sub_cat

                records_result = await db.execute(
                    text(
                        "SELECT is_correct, difficulty, time_spent, "
                        "created_at "
                        "FROM learning_records "
                        "WHERE user_id = :uid "
                        "AND ("
                        "  (:sc != '' AND sub_categories = :sc)"
                        "  OR (:sc = '' AND (sub_categories IS NULL OR sub_categories = '') AND category = :cat)"
                        ") "
                        "ORDER BY created_at DESC"
                    ),
                    {"uid": user_id, "sc": query_sc or "", "cat": category},
                )
                records = records_result.fetchall()

                if not records:
                    continue

                mastery, status, streak, best_streak, history = (
                    self._calculate_mastery(records, now)
                )

                types = [r[0] for r in records]
                skills.append(
                    {
                        "skill_code": skill_code,
                        "display_name": sub_cat_display,
                        "category_path": cat_path,
                        "mastery_level": round(mastery, 3),
                        "status": status,
                        "total_attempts": len(records),
                        "correct_count": sum(1 for t in types if t),
                        "recent_streak": streak,
                        "best_streak": best_streak,
                        "first_seen": str(records[-1][3]) if records[-1][3] else None,
                        "last_practiced": str(records[0][3]) if records[0][3] else None,
                        "mastered_at": (
                            history[-1]["date"]
                            if history and status == "mastered"
                            else None
                        ),
                        "evolution_history": history,
                    }
                )

            skills.sort(key=lambda s: s["mastery_level"], reverse=True)
            return skills[:limit]

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