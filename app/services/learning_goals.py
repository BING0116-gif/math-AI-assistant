"""Owner-scoped learning goals with progress derived from canonical facts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func

from app.data.database import get_db_session
from app.data.models import LearningActivitySession, LearningGoal, PracticeAttempt, UserKnowledgeState


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def list_goals(user_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        goals = list((await db.execute(select(LearningGoal).where(
            LearningGoal.user_id == user_id, LearningGoal.status == "active"
        ).order_by(LearningGoal.created_at, LearningGoal.id))).scalars())
        output = []
        for goal in goals:
            start = _utc(goal.created_at) or now
            if goal.goal_type == "minutes":
                active = await db.scalar(select(func.coalesce(func.sum(LearningActivitySession.active_seconds), 0)).where(
                    LearningActivitySession.user_id == user_id,
                    LearningActivitySession.started_at >= start,
                ))
                current = float(active or 0) / 60.0
                unit = "minutes"
            elif goal.goal_type == "attempts":
                current = float(await db.scalar(select(func.count(PracticeAttempt.id)).where(
                    PracticeAttempt.user_id == user_id,
                    PracticeAttempt.submitted_at >= start,
                )) or 0)
                unit = "attempts"
            else:
                stmt = select(UserKnowledgeState.mastery).where(UserKnowledgeState.user_id == user_id)
                if goal.target_knowledge_point:
                    stmt = stmt.where(UserKnowledgeState.knowledge_point_code == goal.target_knowledge_point)
                values = list((await db.execute(stmt)).scalars())
                current = float(sum(values) / len(values)) if values else 0.0
                unit = "mastery"
            target = float(goal.target_value)
            percent = min(100, round(current / target * 100)) if target else 0
            deadline = _utc(goal.deadline)
            output.append({
                "id": goal.id, "title": goal.title, "goal_type": goal.goal_type,
                "target_value": target, "current_value": round(current, 3),
                "unit": unit, "percent": percent, "status": "completed" if percent >= 100 else "active",
                "target_knowledge_point": goal.target_knowledge_point,
                "deadline": deadline.isoformat() if deadline else None,
                "created_at": start.isoformat(),
            })
        return output


async def create_goal(user_id: str, *, title: str, goal_type: str, target_value: float,
                      target_knowledge_point: str | None = None, deadline: datetime | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        goal = LearningGoal(
            user_id=user_id, title=title.strip(), goal_type=goal_type,
            target_value=target_value, target_knowledge_point=target_knowledge_point,
            deadline=deadline,
        )
        db.add(goal)
        await db.commit()
        await db.refresh(goal)
    items = await list_goals(user_id)
    return next(item for item in items if item["id"] == goal.id)


async def archive_goal(user_id: str, goal_id: str) -> bool:
    async with get_db_session() as db:
        goal = await db.scalar(select(LearningGoal).where(
            LearningGoal.id == goal_id, LearningGoal.user_id == user_id,
        ))
        if goal is None:
            return False
        goal.status = "archived"
        await db.commit()
        return True

