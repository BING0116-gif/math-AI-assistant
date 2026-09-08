from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict
import statistics
import logging

from sqlalchemy import select, func, and_, Integer, desc, extract, cast, case, Float

from app.data.models import LearningRecord, ChatSession

logger = logging.getLogger(__name__)


def _ensure_tz_aware(dt):
    from datetime import timezone as tz
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz.utc)
    return dt


class UserProfileAnalyzer:
    def __init__(self, db_session_factory):
        from app.services.memory import LongTermMemory

        self._session_factory = db_session_factory
        self.memory = LongTermMemory(db_session_factory)

    async def analyze(self, user_id: str) -> Dict[str, Any]:
        profile = await self.memory.get_user_profile(user_id)

        profile.update(await self._analyze_behavior_patterns(user_id))
        profile.update(await self._analyze_error_patterns(user_id))
        profile.update(await self._analyze_progress_trends(user_id))
        profile.update(await self._analyze_preferences(user_id))
        profile.update(self._generate_recommendations(profile))

        return profile

    async def _analyze_behavior_patterns(
        self, user_id: str
    ) -> Dict[str, Any]:
        daily_stats = await self._get_daily_statistics(user_id)
        hourly_stats = await self._get_hourly_statistics(user_id)

        peak_hour = (
            max(hourly_stats.items(), key=lambda x: x[1])[0]
            if hourly_stats
            else 20
        )

        avg_daily_minutes = (
            sum(daily_stats.values()) / max(len(daily_stats), 1)
        )

        streak = await self._calculate_streak(user_id)

        return {
            "behavior": {
                "avg_daily_minutes": round(avg_daily_minutes, 1),
                "peak_hour": f"{peak_hour:02d}:00",
                "active_hours": self._format_active_hours(hourly_stats),
                "learning_streak": streak,
                "total_days_analyzed": len(daily_stats),
            }
        }

    async def _analyze_error_patterns(
        self, user_id: str
    ) -> Dict[str, Any]:
        async with self._session_factory() as db:
            error_query = select(LearningRecord).where(
                and_(
                    LearningRecord.user_id == user_id,
                    LearningRecord.is_correct == False,
                )
            )
            error_result = await db.execute(error_query)
            errors = error_result.scalars().all()

            if not errors:
                return {"error_patterns": {}}

            error_types = defaultdict(int)
            for e in errors:
                error_type = e.error_category or "unknown"
                error_types[error_type] += 1

            total_errors = len(errors)
            error_type_dist = {
                k: round(v / total_errors * 100, 1)
                for k, v in sorted(
                    error_types.items(), key=lambda x: -x[1]
                )
            }

            error_reasons = defaultdict(int)
            for e in errors:
                if e.error_reason:
                    error_reasons[e.error_reason[:50]] += 1

            common_errors = sorted(
                error_reasons.items(), key=lambda x: -x[1]
            )[:5]

        return {
            "error_patterns": {
                "total_errors": total_errors,
                "error_type_distribution": error_type_dist,
                "common_error_reasons": [
                    {"reason": r, "count": c} for r, c in common_errors
                ],
            }
        }

    async def _analyze_progress_trends(
        self, user_id: str
    ) -> Dict[str, Any]:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        async with self._session_factory() as db:
            trend_query = (
                select(LearningRecord)
                .where(
                    and_(
                        LearningRecord.user_id == user_id,
                        LearningRecord.created_at >= thirty_days_ago,
                        LearningRecord.is_correct.isnot(None),
                    )
                )
                .order_by(desc(LearningRecord.created_at))
            )
            trend_result = await db.execute(trend_query)
            records = trend_result.scalars().all()

        if len(records) < 10:
            return {"progress_trends": {"insufficient_data": True}}

        window_size = 7
        correct_rates = []

        for i in range(0, len(records), window_size):
            window = records[i : i + window_size]
            if len(window) > 0:
                correct = sum(1 for r in window if r.is_correct)
                rate = correct / len(window)
                correct_rates.append(rate)

        if len(correct_rates) >= 2:
            trend_slope = self._linear_regression_slope(correct_rates)
            if trend_slope > 0.01:
                trend_direction = "↑"
            elif trend_slope < -0.01:
                trend_direction = "↓"
            else:
                trend_direction = "→"
            trend_percentage = abs(trend_slope) * 100
        else:
            trend_direction = "→"
            trend_percentage = 0

        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        two_weeks_ago = one_week_ago - timedelta(days=7)

        this_week = [r for r in records if _ensure_tz_aware(r.created_at) >= one_week_ago]
        last_week = [
            r
            for r in records
            if two_weeks_ago <= _ensure_tz_aware(r.created_at) < one_week_ago
        ]

        this_week_rate = (
            sum(1 for r in this_week if r.is_correct) / len(this_week)
            if this_week
            else 0
        )
        last_week_rate = (
            sum(1 for r in last_week if r.is_correct) / len(last_week)
            if last_week
            else 0
        )

        week_over_week_change = this_week_rate - last_week_rate

        return {
            "progress_trends": {
                "trend_direction": trend_direction,
                "trend_percentage": round(trend_percentage, 1),
                "this_week_correct_rate": round(this_week_rate, 2),
                "last_week_correct_rate": round(last_week_rate, 2),
                "week_over_week_change": round(
                    week_over_week_change * 100, 1
                ),
                "data_points": len(records),
            }
        }

    async def _analyze_preferences(
        self, user_id: str
    ) -> Dict[str, Any]:
        async with self._session_factory() as db:
            type_query = (
                select(
                    LearningRecord.event_type.label("qtype"),
                    func.count().label("count"),
                )
                .where(LearningRecord.user_id == user_id)
                .group_by(LearningRecord.event_type)
            )
            type_result = await db.execute(type_query)
            type_rows = type_result.all()

            total = sum(row.count for row in type_rows)
            type_preference = (
                {
                    row.qtype: round(row.count / total * 100, 1)
                    for row in type_rows
                }
                if total > 0
                else {}
            )

            diff_query = (
                select(
                    LearningRecord.difficulty,
                    func.count().label("count"),
                    func.avg(cast(
                        case((LearningRecord.is_correct == True, 1), else_=0),
                        Float,
                    )).label(
                        "accuracy"
                    ),
                )
                .where(LearningRecord.user_id == user_id)
                .group_by(LearningRecord.difficulty)
            )
            diff_result = await db.execute(diff_query)
            diff_rows = diff_result.all()

            difficulty_preference = {}
            best_accuracy_diff = 1
            best_accuracy = 0

            for row in diff_rows:
                accuracy = row.accuracy or 0
                difficulty_preference[int(row.difficulty)] = {
                    "count": row.count,
                    "accuracy": round(accuracy, 2),
                }
                if accuracy > best_accuracy and row.count >= 5:
                    best_accuracy = accuracy
                    best_accuracy_diff = int(row.difficulty)

        preferred_type = (
            max(type_preference.items(), key=lambda x: x[1])[0]
            if type_preference
            else "unknown"
        )

        return {
            "preferences": {
                "question_type": type_preference,
                "difficulty": difficulty_preference,
                "preferred_difficulty": best_accuracy_diff,
                "preferred_question_type": preferred_type,
            }
        }

    def _generate_recommendations(
        self, base_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        recommendations = []

        weak_points = base_profile.get("weak_points", [])
        if weak_points:
            weakest = weak_points[0]["category"]
            mastery = weak_points[0].get("mastery", 0)
            recommendations.append(
                {
                    "type": "improvement",
                    "priority": "high",
                    "message": f"重点加强「{weakest}」(当前掌握度: {mastery:.0%})",
                    "action": "practice",
                    "target_category": weakest,
                }
            )

        current_rec = base_profile.get("recommended_difficulty", 3)
        correct_rate = base_profile.get("correct_rate", 0.5)

        if correct_rate > 0.85 and current_rec < 5:
            recommendations.append(
                {
                    "type": "challenge",
                    "priority": "medium",
                    "message": f"你的正确率已达到 {correct_rate:.0%}，可以尝试更高难度的题目",
                    "action": "increase_difficulty",
                    "target_difficulty": current_rec + 1,
                }
            )
        elif correct_rate < 0.5 and current_rec > 1:
            recommendations.append(
                {
                    "type": "review",
                    "priority": "high",
                    "message": "建议先巩固基础，降低练习难度",
                    "action": "decrease_difficulty",
                    "target_difficulty": max(1, current_rec - 1),
                }
            )

        behavior = base_profile.get("behavior", {})
        avg_daily = behavior.get("avg_daily_minutes", 0)

        if avg_daily < 15:
            recommendations.append(
                {
                    "type": "habit",
                    "priority": "low",
                    "message": "每天至少练习 15 分钟才能保持学习效果",
                    "action": "increase_practice_time",
                    "target_minutes": 30,
                }
            )

        return {"recommendations": recommendations}

    async def _get_daily_statistics(
        self, user_id: str
    ) -> Dict[str, int]:
        async with self._session_factory() as db:
            query = (
                select(
                    func.date(LearningRecord.created_at).label("day"),
                    func.count().label("count"),
                )
                .where(LearningRecord.user_id == user_id)
                .group_by(func.date(LearningRecord.created_at))
                .order_by(func.date(LearningRecord.created_at).desc())
                .limit(30)
            )
            result = await db.execute(query)
            rows = result.all()
            return {str(row.day): row.count for row in rows}

    async def _get_hourly_statistics(
        self, user_id: str
    ) -> Dict[int, int]:
        async with self._session_factory() as db:
            query = (
                select(
                    extract("hour", LearningRecord.created_at).label("hour"),
                    func.count().label("count"),
                )
                .where(LearningRecord.user_id == user_id)
                .group_by(extract("hour", LearningRecord.created_at))
            )
            result = await db.execute(query)
            rows = result.all()
            return {int(row.hour): row.count for row in rows}

    async def _calculate_streak(self, user_id: str) -> int:
        daily_stats = await self._get_daily_statistics(user_id)
        if not daily_stats:
            return 0

        dates = sorted(
            datetime.strptime(d, "%Y-%m-%d") for d in daily_stats.keys()
        )
        if not dates:
            return 0

        streak = 1
        today = datetime.now(timezone.utc).date()
        date_set = {d.date() for d in dates}

        check_date = today - timedelta(days=1)
        while check_date in date_set:
            streak += 1
            check_date -= timedelta(days=1)

        return streak

    def _format_active_hours(self, hourly_stats: Dict[int, int]) -> str:
        if not hourly_stats:
            return "暂无数据"

        active_hours = sorted(
            hourly_stats.items(), key=lambda x: -x[1]
        )[:3]
        ranges = []
        for hour, count in active_hours:
            ranges.append(
                f"{hour:02d}:00-{(hour + 1) % 24:02d}:00 ({count}次)"
            )
        return ", ".join(ranges)

    def _linear_regression_slope(self, y_values: List[float]) -> float:
        n = len(y_values)
        if n < 2:
            return 0

        x_mean = (n - 1) / 2
        y_mean = statistics.mean(y_values)

        numerator = sum(
            (i - x_mean) * (y - y_mean) for i, y in enumerate(y_values)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        return numerator / denominator if denominator != 0 else 0