"""Deterministic, owner-scoped daily learning plan service."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any
import uuid
from sqlalchemy import select, func, or_
from app.data.database import get_db_session
from app.data.models import (LearningPlan, LearningPlanTask, LearningGoal, Question,
                             UserKnowledgeState, LearningRecord, ReviewSchedule, ErrorItem)

class PlanError(Exception):
    def __init__(self, code: str, message: str): self.code, self.message = code, message

def _date(now=None):
    now = now or datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

def _task(t):
    return {"id": t.id, "plan_id": t.plan_id, "task_type": t.task_type, "knowledge_point": t.knowledge_point,
            "question_id": t.question_id, "sequence": t.sequence, "status": t.status,
            "attempt_count": t.attempt_count, "started_at": t.started_at, "completed_at": t.completed_at,
            "failure_reason": t.failure_reason, "estimated_minutes": t.estimated_minutes}

def _plan(p, tasks):
    return {"id": p.id, "user_id": p.user_id, "plan_date": p.plan_date, "goal_id": p.goal_id,
            "status": p.status, "estimated_minutes": p.estimated_minutes, "completed_minutes": p.completed_minutes,
            "created_at": p.created_at, "updated_at": p.updated_at, "tasks": [_task(t) for t in tasks]}

async def get_today_plan(user_id: str) -> dict[str, Any] | None:
    async with get_db_session() as db:
        p = await db.scalar(select(LearningPlan).where(LearningPlan.user_id == user_id, LearningPlan.plan_date == _date()))
        if not p: return None
        tasks = list((await db.scalars(select(LearningPlanTask).where(LearningPlanTask.plan_id == p.id, LearningPlanTask.user_id == user_id).order_by(LearningPlanTask.sequence))).all())
        return _plan(p, tasks)

async def generate_plan(user_id: str, *, goal_id: str | None = None, available_minutes: int = 30) -> dict[str, Any]:
    available_minutes = max(5, min(int(available_minutes), 240))
    today = _date()
    async with get_db_session() as db:
        existing = await db.scalar(select(LearningPlan).where(LearningPlan.user_id == user_id, LearningPlan.plan_date == today))
        if existing:
            tasks = list((await db.scalars(select(LearningPlanTask).where(LearningPlanTask.plan_id == existing.id, LearningPlanTask.user_id == user_id).order_by(LearningPlanTask.sequence))).all())
            return _plan(existing, tasks)
        goal = None
        if goal_id:
            goal = await db.scalar(select(LearningGoal).where(LearningGoal.id == goal_id, LearningGoal.user_id == user_id, LearningGoal.status == "active"))
            if not goal: raise PlanError("GOAL_NOT_FOUND", "学习目标不存在")
        else:
            goal = await db.scalar(select(LearningGoal).where(LearningGoal.user_id == user_id, LearningGoal.status == "active").order_by(LearningGoal.created_at, LearningGoal.id))
        budget = max(1, available_minutes // 5)
        states = list((await db.scalars(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id).order_by(UserKnowledgeState.mastery, UserKnowledgeState.knowledge_point_code))).all())
        target_mastery = (float(goal.target_value) / 100 if goal and goal.goal_type == "mastery" and goal.target_value > 1 else float(goal.target_value) if goal and goal.goal_type == "mastery" else 1.0)
        weak_codes = [s.knowledge_point_code for s in states if s.mastery < target_mastery]
        if goal and goal.target_knowledge_point:
            weak_codes = [goal.target_knowledge_point] + [x for x in weak_codes if x != goal.target_knowledge_point]
        # Priority is explicit and deterministic: due review, error item, weak mastery, then goal/new practice.
        due_codes = list((await db.scalars(select(ReviewSchedule.knowledge_point_code).where(ReviewSchedule.user_id == user_id, or_(ReviewSchedule.due_at <= datetime.now(timezone.utc), ReviewSchedule.deferred_until <= datetime.now(timezone.utc))).order_by(ReviewSchedule.due_at))).all())
        error_rows = list((await db.scalars(select(ErrorItem).where(ErrorItem.user_id == user_id, ErrorItem.is_mastered.is_(False)).order_by(ErrorItem.last_reviewed_at, ErrorItem.id).limit(budget))).all())
        priority_codes = []
        for code in due_codes + [c for e in error_rows for c in (e.knowledge_point_codes or [])] + weak_codes:
            if code and code not in priority_codes: priority_codes.append(code)
        if not priority_codes: priority_codes = [goal.target_knowledge_point] if goal and goal.target_knowledge_point else ["general_diagnostic"]
        # Do not repeat questions already used by this user's plan history.
        used_ids = set((await db.scalars(select(LearningPlanTask.question_id).where(LearningPlanTask.user_id == user_id, LearningPlanTask.question_id.is_not(None)))).all())
        questions = []
        error_question_ids = [e.question_id for e in error_rows if e.question_id]
        if error_question_ids:
            for q in (await db.scalars(select(Question).where(Question.id.in_(error_question_ids), Question.is_active.is_(True), Question.review_status == "published"))).all():
                if q.id not in used_ids: questions.append(q)
                if len(questions) >= budget: break
        for code in priority_codes:
            stmt = select(Question).where(Question.is_active.is_(True), Question.review_status == "published",
                (Question.knowledge_points.like(f"%{code}%")) | (Question.category == code))
            for q in (await db.scalars(stmt.order_by(Question.difficulty, Question.id).limit(budget))).all():
                if q.id not in used_ids and q.id not in {x.id for x in questions}: questions.append(q)
                if len(questions) >= budget: break
            if len(questions) >= budget: break
        # If all matching questions were used, deterministic fallback still avoids random selection.
        if not questions:
            questions = list((await db.scalars(select(Question).where(Question.is_active.is_(True), Question.review_status == "published").order_by(Question.difficulty, Question.id).limit(budget))).all())
        count = max(1, min(available_minutes // 5, len(questions) or 1))
        if goal and goal.deadline:
            days_left = max(1, (_date(goal.deadline) - today).days + 1)
            # Keep daily work bounded by the remaining deadline while honoring the requested budget.
            count = min(count, max(1, int((available_minutes * days_left) / days_left // 5)))
        p = LearningPlan(id=str(uuid.uuid4()), user_id=user_id, plan_date=today, goal_id=goal.id if goal else None, estimated_minutes=count * 5)
        db.add(p); await db.flush()
        tasks = []
        for i in range(count):
            q = questions[i] if i < len(questions) else None
            t = LearningPlanTask(id=str(uuid.uuid4()), plan_id=p.id, user_id=user_id,
                                 task_type="diagnostic" if q is None else "practice",
                                 knowledge_point=(priority_codes[i % len(priority_codes)] if priority_codes else (q.category if q else "general_diagnostic")),
                                 question_id=q.id if q else None, sequence=i + 1, estimated_minutes=5)
            db.add(t); tasks.append(t)
        await db.commit(); await db.refresh(p)
        return _plan(p, tasks)

async def update_task(user_id: str, plan_id: str, task_id: str, action: str) -> dict[str, Any]:
    async with get_db_session() as db:
        t = await db.scalar(select(LearningPlanTask).where(LearningPlanTask.id == task_id, LearningPlanTask.plan_id == plan_id, LearningPlanTask.user_id == user_id))
        if not t: raise PlanError("TASK_NOT_FOUND", "计划任务不存在")
        now = datetime.now(timezone.utc)
        if action == "start":
            if t.status in {"completed", "skipped", "expired"}: raise PlanError("TASK_NOT_ACTIONABLE", "任务已结束")
            t.status = "in_progress"; t.started_at = t.started_at or now; t.attempt_count += 1; t.failure_reason = None
        elif action in {"complete", "skip", "fail"}:
            if t.status in {"completed", "skipped"}: return _task(t)
            t.status = "completed" if action == "complete" else "failed" if action == "fail" else "skipped"; t.completed_at = now if action != "fail" else None
            if action == "fail": t.failure_reason = "task_failed"
            if action == "complete":
                p = await db.get(LearningPlan, plan_id)
                p.completed_minutes = (p.completed_minutes or 0) + t.estimated_minutes
                if p.completed_minutes >= p.estimated_minutes: p.status = "completed"
                # Completion is an append-only learning fact. Correctness is deliberately
                # left unset until a real attempt is submitted, so plan completion cannot
                # inflate mastery metrics.
                if t.question_id:
                    q = await db.get(Question, t.question_id)
                    if q:
                        db.add(LearningRecord(user_id=user_id, question_id=q.id, event_type="plan_task_completed",
                                              question_content=q.content, category=q.category, difficulty=q.difficulty,
                                              metadata_={"plan_id": plan_id, "task_id": task_id}))
                if t.knowledge_point:
                    state = await db.scalar(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id, UserKnowledgeState.knowledge_point_code == t.knowledge_point))
                    if state:
                        state.last_reviewed_at = now
        else: raise PlanError("INVALID_ACTION", "不支持的任务操作")
        await db.commit(); await db.refresh(t); return _task(t)

async def resume_plan(user_id: str, plan_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        p = await db.scalar(select(LearningPlan).where(LearningPlan.id == plan_id, LearningPlan.user_id == user_id))
        if not p: raise PlanError("PLAN_NOT_FOUND", "学习计划不存在")
        p.status = "active"
        for t in (await db.scalars(select(LearningPlanTask).where(LearningPlanTask.plan_id == p.id, LearningPlanTask.user_id == user_id, LearningPlanTask.status == "failed"))).all(): t.status = "pending"; t.failure_reason = None
        await db.commit(); tasks = list((await db.scalars(select(LearningPlanTask).where(LearningPlanTask.plan_id == p.id, LearningPlanTask.user_id == user_id).order_by(LearningPlanTask.sequence))).all()); return _plan(p, tasks)
