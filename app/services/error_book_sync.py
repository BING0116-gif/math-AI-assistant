from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.data.database import get_db_session

logger = logging.getLogger(__name__)


class ErrorBookSkillSyncService:
    """
    错题本 ↔ Skill 系统双向同步服务。

    功能:
    1. 错题本新增/更新时 → 写入 learning_records + 触发 SkillAggregator 重算
    2. 错题本状态变化时 → 更新学习事实并重算 UserKnowledgeState
    3. 批量同步：将历史错题本数据一次性导入 skill 系统
    """

    def __init__(self):
        self._skill_aggregator = None
        self._behavior_tracker = None

    def _get_skill_aggregator(self):
        if not self._skill_aggregator:
            from app.services.skill_aggregator import SkillAggregator
            self._skill_aggregator = SkillAggregator()
        return self._skill_aggregator

    def _get_behavior_tracker(self):
        if not self._behavior_tracker:
            from app.services.behavior_tracker import LearningBehaviorTracker
            self._behavior_tracker = LearningBehaviorTracker()
        return self._behavior_tracker

    async def on_error_added(
        self, user_id: str, error_entry: Dict[str, Any]
    ) -> Dict[str, Any]:
        tracker = self._get_behavior_tracker()
        event = tracker.from_error_book_entry(user_id, error_entry)

        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()

        success = await facade.record_event(user_id, event)

        agg = self._get_skill_aggregator()
        updated = await agg.recalculate_skills(user_id)

        result = {
            "synced_to_learning_records": success,
            "skills_recalculated": updated,
            "event_category": event.get("category"),
            "event_type": event.get("event_type"),
        }
        logger.info(
            f"ErrorBook sync on_add: user={user_id}, "
            f"category={event.get('category')}, skills_updated={updated}"
        )
        return result

    async def on_error_mastery_toggled(
        self, user_id: str, error_id: str, is_mastered: bool
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            from sqlalchemy import select
            from app.data.models import LearningRecord

            result = await db.execute(
                select(LearningRecord).where(
                    LearningRecord.user_id == user_id,
                    LearningRecord.metadata_["error_book_id"].as_string() == error_id,
                )
            )
            records = result.scalars().all()

            for record in records:
                metadata = dict(record.metadata_ or {})
                metadata["error_book_mastery"] = str(is_mastered)
                record.metadata_ = metadata

                # 手动自评只更新元数据，不改写历史答题结果或事件类型。

            await db.commit()

        agg = self._get_skill_aggregator()
        updated = await agg.recalculate_skills(user_id)

        logger.info(
            f"ErrorBook mastery toggle: user={user_id}, "
            f"error={error_id}, mastered={is_mastered}, skills_updated={updated}"
        )

        return {
            "error_id": error_id,
            "is_mastered": is_mastered,
            "skills_recalculated": updated,
        }

    async def batch_sync(
        self, user_id: str, error_entries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        tracker = self._get_behavior_tracker()
        facade = MemoryPersistenceFacade()

        synced = 0
        categories_seen = set()

        for entry in error_entries:
            event = tracker.from_error_book_entry(user_id, entry)
            success = await facade.record_event(user_id, event)
            if success:
                synced += 1
            if event.get("category"):
                categories_seen.add(event["category"])

        agg = self._get_skill_aggregator()
        skills_updated = await agg.recalculate_skills(user_id)

        return {
            "total_entries": len(error_entries),
            "synced_records": synced,
            "categories_covered": list(categories_seen),
            "skills_recalculated": skills_updated,
        }

    async def get_skill_impact_summary(
        self, user_id: str
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            from sqlalchemy import text

            result = await db.execute(
                text("""
                    SELECT
                        COUNT(*) as total_errors,
                        COUNT(CASE WHEN is_mastered=1 THEN 1 END) as mastered_count,
                        COUNT(CASE WHEN is_mastered=0 OR is_mastered IS NULL THEN 1 END) as unmastered_count
                    FROM learning_records
                    WHERE user_id = :uid AND source = 'error_book'
                """),
                {"uid": user_id},
            )
            row = result.fetchone()

            weak_result = await db.execute(
                text("""
                    SELECT category, COUNT(*) as cnt
                    FROM learning_records
                    WHERE user_id = :uid
                      AND source = 'error_book'
                      AND (is_mastered = 0 OR is_mastered IS NULL)
                    GROUP BY category
                    ORDER BY cnt DESC
                    LIMIT 5
                """),
                {"uid": user_id},
            )
            weak_categories = [
                {"category": r[0], "count": r[1]} for r in weak_result.fetchall()
            ]

        return {
            "total_error_records": row[0] if row else 0,
            "mastered_errors": row[1] if row else 0,
            "unmastered_errors": row[2] if row else 0,
            "weak_categories": weak_categories,
        }
