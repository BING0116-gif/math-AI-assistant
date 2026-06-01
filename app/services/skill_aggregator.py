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
        from sqlalchemy import text

        async with self._session_factory() as db:
            result = await db.execute(
                text(
                    "SELECT skill_code, display_name, category_path, "
                    "mastery_level, status, total_attempts, correct_count, "
                    "recent_streak, best_streak, last_practiced_at, "
                    "first_seen_at, mastered_at, evolution_history "
                    "FROM user_skills WHERE user_id = :uid "
                    "ORDER BY mastery_level DESC LIMIT :limit"
                ),
                {"uid": user_id, "limit": max_skills},
            )
            rows = result.fetchall()

            if rows:
                return [
                    {
                        "skill_code": r[0],
                        "display_name": r[1],
                        "category_path": r[2],
                        "mastery_level": r[3],
                        "status": r[4],
                        "total_attempts": r[5],
                        "correct_count": r[6],
                        "recent_streak": r[7],
                        "best_streak": r[8],
                        "last_practiced": (
                            r[9].isoformat() if r[9] else None
                        ),
                        "first_seen": r[10].isoformat() if r[10] else None,
                        "mastered_at": r[11].isoformat() if r[11] else None,
                        "evolution_history": (
                            json.loads(r[12]) if r[12] else []
                        ),
                    }
                    for r in rows
                ]

            return await self._compute_skills(user_id, max_skills)

    async def recalculate_skills(
        self, user_id: str, skill_codes: Optional[List[str]] = None
    ) -> int:
        skills = await self._compute_skills(user_id)

        filtered = skills
        if skill_codes:
            filtered = [s for s in skills if s["skill_code"] in skill_codes]

        from sqlalchemy import text
        async with self._session_factory() as db:
            for skill in filtered:
                await db.execute(
                    text(
                        "INSERT INTO user_skills (user_id, skill_code, "
                        "display_name, category_path, mastery_level, status, "
                        "total_attempts, correct_count, recent_streak, "
                        "best_streak, first_seen_at, last_practiced_at, "
                        "mastered_at, evolution_history, updated_at) "
                        "VALUES (:uid, :sc, :dn, :cp, :ml, :st, :ta, :cc, "
                        ":rs, :bs, :fs, :lp, :ma, :eh, CURRENT_TIMESTAMP) "
                        "ON CONFLICT (user_id, skill_code) DO UPDATE SET "
                        "mastery_level = EXCLUDED.mastery_level, "
                        "status = EXCLUDED.status, "
                        "total_attempts = EXCLUDED.total_attempts, "
                        "correct_count = EXCLUDED.correct_count, "
                        "recent_streak = EXCLUDED.recent_streak, "
                        "best_streak = EXCLUDED.best_streak, "
                        "last_practiced_at = EXCLUDED.last_practiced_at, "
                        "evolution_history = EXCLUDED.evolution_history, "
                        "updated_at = CURRENT_TIMESTAMP"
                    ),
                    {
                        "uid": user_id,
                        "sc": skill["skill_code"],
                        "dn": skill["display_name"],
                        "cp": skill.get("category_path", ""),
                        "ml": skill["mastery_level"],
                        "st": skill["status"],
                        "ta": skill["total_attempts"],
                        "cc": skill["correct_count"],
                        "rs": skill["recent_streak"],
                        "bs": skill["best_streak"],
                        "fs": skill.get("first_seen"),
                        "lp": skill.get("last_practiced"),
                        "ma": skill.get("mastered_at"),
                        "eh": json.dumps(
                            skill.get("evolution_history", []),
                            ensure_ascii=False,
                        ),
                    },
                )
            await db.commit()
        return len(filtered)

    async def get_error_patterns(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        async with self._session_factory() as db:
            result = await db.execute(
                text(
                    "SELECT error_reason, COUNT(*) as freq, "
                    "GROUP_CONCAT(DISTINCT category) as affected "
                    "FROM learning_records "
                    "WHERE user_id = :uid AND is_correct = FALSE "
                    "AND error_reason IS NOT NULL AND error_reason != '' "
                    "GROUP BY error_reason "
                    "HAVING COUNT(DISTINCT category) >= 2 "
                    "ORDER BY freq DESC "
                    "LIMIT 10"
                ),
                {"uid": user_id},
            )
            rows = result.fetchall()

            total_errors = sum(r[1] for r in rows) or 1
            return [
                {
                    "pattern": r[0],
                    "frequency": round(r[1] / total_errors, 2),
                    "affected_skills": r[2].split(",") if r[2] else [],
                }
                for r in rows
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
            result = await db.execute(
                text(
                    "SELECT DISTINCT sub_categories, category "
                    "FROM learning_records "
                    "WHERE user_id = :uid AND sub_categories IS NOT NULL "
                    "AND sub_categories != ''"
                ),
                {"uid": user_id},
            )
            skill_rows = result.fetchall()

            skills = []
            now = datetime.now(timezone.utc)

            for row in skill_rows:
                sub_cat = row[0]
                category = row[1]
                skill_code = self._derive_skill_code(category, sub_cat)

                records_result = await db.execute(
                    text(
                        "SELECT is_correct, difficulty, time_spent, "
                        "created_at "
                        "FROM learning_records "
                        "WHERE user_id = :uid "
                        "AND (sub_categories = :sc OR category = :cat) "
                        "ORDER BY created_at DESC"
                    ),
                    {"uid": user_id, "sc": sub_cat, "cat": category},
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
                        "display_name": sub_cat,
                        "category_path": f"{category} > {sub_cat}",
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