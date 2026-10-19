"""Privacy-safe, explainable learning-effectiveness aggregates.

The source events are existing owner-bound tables.  This module deliberately
returns counts/rates only; no user id, question text, answer, or raw AI output
is included in the report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from app.data.database import get_db_session
from app.data.models import (
    AIInteractionRun, ErrorReviewEvent, LearningRecord, PracticeAttempt,
    ReviewSchedule, ReviewScheduleAction, User, UserKnowledgeState, ErrorItem,
    LearningPlan, LearningPlanTask,
)

EVENT_CONTRACT = {
    "activity": {"source": "learning_activity_sessions", "fields": ["user_id", "started_at", "ended_at", "active_seconds"], "scope": "active students", "privacy": "aggregate only; user_id never leaves SQL"},
    "practice": {"source": "practice_attempts", "fields": ["user_id", "submitted_at", "correct", "knowledge_point_codes", "attempt_kind"], "scope": "attempt owner", "privacy": "aggregate only; no answers or question content"},
    "review": {"source": "error_review_events/review_schedule_actions", "fields": ["user_id", "created_at", "event_type", "action"], "scope": "attempt owner", "privacy": "aggregate only; counts only"},
    "ai_feedback": {"source": "ai_interaction_runs", "fields": ["user_id", "created_at", "status", "modified_by_user"], "scope": "run owner", "privacy": "aggregate only; no prompt/output; low-cardinality fields only"},
    "mastery": {"source": "user_knowledge_states", "fields": ["user_id", "knowledge_point_code", "mastery", "updated_at"], "scope": "state owner", "privacy": "aggregate only; report mean delta and sample size"},
}

def _day(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

async def build_learning_effectiveness(*, as_of: datetime | None = None, days: int = 30) -> dict[str, Any]:
    """Build a bounded report. Rates are ``None`` when their denominator is 0."""
    now = as_of or datetime.now(timezone.utc)
    start = _day(now) - timedelta(days=max(1, min(days, 365)))
    tomorrow = _day(now) + timedelta(days=1)
    async with get_db_session() as db:
        students = select(User.id).where(or_(User.role != "admin", User.role.is_(None)), User.is_active.is_(True))
        student_ids = (await db.execute(students)).scalars().all()
        activity = (await db.execute(select(LearningRecord.user_id, LearningRecord.created_at).where(LearningRecord.user_id.in_(student_ids or ["__none__"]), LearningRecord.created_at >= start))).all()
        active_by_user: dict[str, set] = {}
        for uid, created in activity:
            active_by_user.setdefault(uid, set()).add(_day(created).date())
        cohort = len(active_by_user)
        retention = {}
        for offset in (1, 7):
            eligible = {uid for uid, dates in active_by_user.items() if (min(dates) + timedelta(days=offset)) <= now.date()}
            retained = sum(1 for uid in eligible if (min(active_by_user[uid]) + timedelta(days=offset)) in active_by_user[uid])
            retention[f"day_{offset}"] = {"numerator": retained, "denominator": len(eligible), "rate": retained / len(eligible) if eligible else None}

        due = int((await db.scalar(select(func.count()).select_from(ReviewSchedule).where(ReviewSchedule.user_id.in_(student_ids or ["__none"]), ReviewSchedule.due_at >= _day(now), ReviewSchedule.due_at < tomorrow))) or 0)
        completed = int((await db.scalar(select(func.count()).select_from(ReviewScheduleAction).where(ReviewScheduleAction.user_id.in_(student_ids or ["__none"]), ReviewScheduleAction.action == "complete", ReviewScheduleAction.created_at >= _day(now), ReviewScheduleAction.created_at < tomorrow))) or 0)
        review_total = int((await db.scalar(select(func.count()).select_from(ErrorReviewEvent).where(ErrorReviewEvent.user_id.in_(student_ids or ["__none"]), ErrorReviewEvent.created_at >= start))) or 0)
        error_items = int((await db.scalar(select(func.count()).select_from(ErrorItem).where(ErrorItem.user_id.in_(student_ids or ["__none"]), ErrorItem.is_mastered.is_(False)))) or 0)
        reviewed_error_items = int((await db.scalar(select(func.count(func.distinct(ErrorReviewEvent.error_item_id))).where(ErrorReviewEvent.user_id.in_(student_ids or ["__none"]), ErrorReviewEvent.created_at >= start))) or 0)
        plan_tasks = int((await db.scalar(select(func.count()).select_from(LearningPlanTask).join(LearningPlan, LearningPlan.id == LearningPlanTask.plan_id).where(LearningPlanTask.user_id.in_(student_ids or ["__none"]), LearningPlan.plan_date >= start, LearningPlan.plan_date < tomorrow))) or 0)
        completed_plan_tasks = int((await db.scalar(select(func.count()).select_from(LearningPlanTask).join(LearningPlan, LearningPlan.id == LearningPlanTask.plan_id).where(LearningPlanTask.user_id.in_(student_ids or ["__none"]), LearningPlan.plan_date >= start, LearningPlan.plan_date < tomorrow, LearningPlanTask.status == "completed"))) or 0)
        interrupted_plan_tasks = int((await db.scalar(select(func.count()).select_from(LearningPlanTask).join(LearningPlan, LearningPlan.id == LearningPlanTask.plan_id).where(LearningPlanTask.user_id.in_(student_ids or ["__none"]), LearningPlan.plan_date >= start, LearningPlan.plan_date < tomorrow, LearningPlanTask.status.in_(["skipped", "failed", "expired"])))) or 0)
        runs = int((await db.scalar(select(func.count()).select_from(AIInteractionRun).where(AIInteractionRun.user_id.in_(student_ids or ["__none"]), AIInteractionRun.status == "completed", AIInteractionRun.created_at >= start))) or 0)
        corrected = int((await db.scalar(select(func.count()).select_from(AIInteractionRun).where(AIInteractionRun.user_id.in_(student_ids or ["__none"]), AIInteractionRun.status == "completed", AIInteractionRun.modified_by_user.is_(True), AIInteractionRun.created_at >= start))) or 0)
        mastery_rows = (await db.execute(select(UserKnowledgeState.mastery, UserKnowledgeState.evolution_history).where(UserKnowledgeState.user_id.in_(student_ids or ["__none"]), UserKnowledgeState.updated_at >= start))).all()
    deltas = []
    for mastery, history in mastery_rows:
        previous = (history or [{}])[-2].get("mastery") if len(history or []) > 1 else None
        if previous is not None: deltas.append(float(mastery) - float(previous))
    return {"as_of": now.isoformat(), "window_days": max(1, min(days, 365)), "population": {"active_students": cohort}, "retention": retention, "today_task_completion": {"numerator": completed, "denominator": due, "rate": completed / due if due else None}, "plan_task_completion": {"numerator": completed_plan_tasks, "denominator": plan_tasks, "rate": completed_plan_tasks / plan_tasks if plan_tasks else None}, "plan_interruption": {"numerator": interrupted_plan_tasks, "denominator": plan_tasks, "rate": interrupted_plan_tasks / plan_tasks if plan_tasks else None}, "error_review_rate": {"numerator": reviewed_error_items, "denominator": error_items, "rate": reviewed_error_items / error_items if error_items else None, "review_events": review_total}, "mastery_change": {"sample_size": len(deltas), "mean_delta": sum(deltas) / len(deltas) if deltas else None}, "ai_answer_adoption": {"numerator": runs - corrected, "denominator": runs, "rate": (runs - corrected) / runs if runs else None}, "ai_answer_correction": {"numerator": corrected, "denominator": runs, "rate": corrected / runs if runs else None}, "event_contract": EVENT_CONTRACT}
