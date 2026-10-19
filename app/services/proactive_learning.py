"""Phase 3 proactive learning jobs.

Jobs only create auditable in-app actions. They never contact an external channel.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import uuid
from sqlalchemy import select, update, or_
from app.data.database import get_db_session
from app.data.models import (User, LearningAutomationPreference, ProactiveLearningAction,
    ReviewSchedule, ErrorItem, LearningGoal, LearningPlan, LearningPlanTask, LearningActivitySession)
from app.services.learning_plan import generate_plan

def _now(value=None): return value or datetime.now(timezone.utc)

async def _enabled(db, user_id: str) -> bool:
    pref = await db.get(LearningAutomationPreference, user_id)
    return pref is None or pref.enabled

async def _action(db, *, user_id, action_type, trigger, evidence, now, cooldown_hours=24, expires_hours=24):
    if not await _enabled(db, user_id): return None
    key = f"{action_type}:{trigger}:{evidence.get('knowledge_point') or evidence.get('goal_id') or 'user'}:{now.date().isoformat()}"
    existing = await db.scalar(select(ProactiveLearningAction).where(ProactiveLearningAction.user_id == user_id, ProactiveLearningAction.frequency_key == key))
    if existing: return existing
    row = ProactiveLearningAction(id=str(uuid.uuid4()), user_id=user_id, action_type=action_type, trigger=trigger,
        evidence=evidence, frequency_key=key, cooldown_hours=cooldown_hours,
        expires_at=now + timedelta(hours=expires_hours))
    db.add(row); return row

async def generate_due_reviews(*, now=None) -> dict[str, int]:
    now = _now(now); made = 0
    async with get_db_session() as db:
        rows = list((await db.scalars(select(ReviewSchedule).where(ReviewSchedule.due_at <= now, or_(ReviewSchedule.deferred_until.is_(None), ReviewSchedule.deferred_until <= now)).limit(500))).all())
        for row in rows:
            action = await _action(db, user_id=row.user_id, action_type="review_reminder", trigger="spaced_review_due",
                evidence={"knowledge_point": row.knowledge_point_code, "last_review_at": row.last_reviewed_at.isoformat() if row.last_reviewed_at else None, "schedule_id": row.id}, now=now)
            made += bool(action)
        await db.commit()
    return {"created": made, "candidates": len(rows)}

async def refresh_daily_plans(*, now=None) -> dict[str, int]:
    now = _now(now); created = 0
    async with get_db_session() as db:
        users = list((await db.scalars(select(User.id).join(LearningGoal, LearningGoal.user_id == User.id).where(LearningGoal.status == "active").distinct())).all())
    for uid in users:
        if await generate_plan(uid): created += 1
    return {"refreshed": created}

async def detect_learning_stall(*, now=None, stall_days=7) -> dict[str, int]:
    now = _now(now); made = 0
    cutoff = now - timedelta(days=stall_days)
    async with get_db_session() as db:
        goals = list((await db.scalars(select(LearningGoal).where(LearningGoal.status == "active"))).all())
        for goal in goals:
            last = await db.scalar(select(LearningActivitySession.last_heartbeat_at).where(LearningActivitySession.user_id == goal.user_id).order_by(LearningActivitySession.last_heartbeat_at.desc()).limit(1))
            if last is None or last < cutoff:
                made += bool(await _action(db, user_id=goal.user_id, action_type="learning_nudge", trigger="learning_stalled", evidence={"goal_id": goal.id, "last_activity_at": last.isoformat() if last else None, "stall_days": stall_days}, now=now))
        await db.commit()
    return {"created": made}

async def detect_repeated_errors(*, now=None, threshold=2) -> dict[str, int]:
    now = _now(now); made = 0
    async with get_db_session() as db:
        rows = list((await db.scalars(select(ErrorItem).where(ErrorItem.is_mastered.is_(False), ErrorItem.wrong_attempt_count >= threshold).limit(500))).all())
        for row in rows:
            kp = (row.knowledge_point_codes or [None])[0]
            made += bool(await _action(db, user_id=row.user_id, action_type="targeted_practice", trigger="repeated_error", evidence={"error_item_id": row.id, "question_id": row.question_id, "knowledge_point": kp, "wrong_attempt_count": row.wrong_attempt_count}, now=now))
        await db.commit()
    return {"created": made, "candidates": len(rows)}

async def send_goal_deadline_reminder(*, now=None, within_days=2) -> dict[str, int]:
    now = _now(now); made = 0
    async with get_db_session() as db:
        until = now + timedelta(days=within_days)
        rows = list((await db.scalars(select(LearningGoal).where(LearningGoal.status == "active", LearningGoal.deadline != None, LearningGoal.deadline >= now, LearningGoal.deadline <= until))).all())
        for row in rows:
            made += bool(await _action(db, user_id=row.user_id, action_type="goal_deadline_reminder", trigger="goal_deadline_soon", evidence={"goal_id": row.id, "deadline": row.deadline.isoformat(), "title": row.title}, now=now, expires_hours=max(1, int((row.deadline - now).total_seconds() / 3600))))
        await db.commit()
    return {"created": made, "candidates": len(rows)}

async def reconcile_plan_task_status(*, now=None) -> dict[str, int]:
    now = _now(now)
    async with get_db_session() as db:
        result = await db.execute(update(LearningPlanTask).where(LearningPlanTask.status.in_(["pending", "in_progress"]), LearningPlanTask.plan_id.in_(select(LearningPlan.id).where(LearningPlan.plan_date < now.replace(hour=0, minute=0, second=0, microsecond=0)))).values(status="expired"))
        await db.execute(update(ProactiveLearningAction).where(ProactiveLearningAction.status.in_(["pending", "failed"]), ProactiveLearningAction.expires_at <= now).values(status="expired"))
        await db.commit()
    return {"expired": result.rowcount or 0}

async def cancel_action(user_id: str, action_id: str) -> bool:
    async with get_db_session() as db:
        row = await db.scalar(select(ProactiveLearningAction).where(ProactiveLearningAction.id == action_id, ProactiveLearningAction.user_id == user_id))
        if not row or row.status in {"delivered", "dead", "expired"}: return False
        row.status = "cancelled"; row.cancelled_at = datetime.now(timezone.utc); await db.commit(); return True

async def retry_action(user_id: str, action_id: str) -> bool:
    """Requeue a failed proactive action owned by the current user."""
    async with get_db_session() as db:
        row = await db.scalar(select(ProactiveLearningAction).where(
            ProactiveLearningAction.id == action_id,
            ProactiveLearningAction.user_id == user_id,
        ))
        if not row or row.status not in {"failed", "dead"} or row.attempts >= row.max_attempts:
            return False
        row.status = "pending"
        row.last_error = None
        await db.commit()
        return True

async def set_automation_enabled(user_id: str, enabled: bool) -> dict[str, Any]:
    async with get_db_session() as db:
        row = await db.get(LearningAutomationPreference, user_id)
        if row is None: row = LearningAutomationPreference(user_id=user_id); db.add(row)
        row.enabled = enabled; await db.commit(); return {"user_id": user_id, "enabled": enabled}

async def record_action_result(action_id: str, *, success: bool, result: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    """Record an authorized in-app delivery result; failures remain retryable until dead-letter."""
    async with get_db_session() as db:
        row = await db.get(ProactiveLearningAction, action_id)
        if row is None: raise ValueError("action not found")
        if row.status in {"cancelled", "expired", "dead"}: return {"status": row.status, "attempts": row.attempts}
        row.attempts += 1; row.result = result or {}
        if success:
            row.status = "delivered"; row.last_error = None
        else:
            row.last_error = (error or "delivery failed")[:500]
            row.status = "dead" if row.attempts >= row.max_attempts else "failed"
        await db.commit(); return {"status": row.status, "attempts": row.attempts, "id": row.id}
