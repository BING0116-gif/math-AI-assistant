"""SQL-only learning hub for spaced review, explainable tasks and dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from app.data.database import get_db_session
from app.data.models import (
    Chapter, KnowledgePoint, LearningActivitySession, PracticeAttempt, Question,
    QuestionKnowledgePoint, ReviewSchedule, ReviewScheduleAction, UserKnowledgeState,
)

from app.services.learning_projection import read_learning_states, state_evidence
from app.services.mastery_evidence import evidence_summary

RECOMMENDATION_VERSION = "today-rules-v1"
SPACED_INTERVALS = (1, 3, 7, 15)


class LearningHubError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _schedule_payload(row: ReviewSchedule, name: str | None = None) -> dict[str, Any]:
    effective_due = max(filter(None, (_utc(row.due_at), _utc(row.deferred_until))))
    return {
        "id": row.id, "knowledge_point_code": row.knowledge_point_code,
        "knowledge_point_name": name or row.knowledge_point_code,
        "due_at": effective_due.isoformat(), "interval_days": row.interval_days,
        "review_count": row.review_count, "stage": row.stage,
        "algorithm_version": row.algorithm_version,
    }


async def due_reviews(user_id: str, *, limit: int = 20, include_upcoming: bool = False) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        stmt = select(ReviewSchedule).where(ReviewSchedule.user_id == user_id)
        if not include_upcoming:
            stmt = stmt.where(ReviewSchedule.due_at <= now).where(
                or_(ReviewSchedule.deferred_until.is_(None), ReviewSchedule.deferred_until <= now)
            )
        rows = list((await db.execute(stmt.order_by(ReviewSchedule.due_at, ReviewSchedule.id).limit(limit))).scalars())
        codes = [row.knowledge_point_code for row in rows]
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.code.in_(codes or ["__none__"])))).scalars())
        names = {point.code: point.name for point in points}
    return {"generated_at": now, "items": [_schedule_payload(row, names.get(row.knowledge_point_code)) for row in rows]}


async def defer_review(user_id: str, schedule_id: int, *, hours: int, idempotency_key: str) -> dict[str, Any]:
    async with get_db_session() as db:
        prior = (await db.execute(select(ReviewScheduleAction).where(
            ReviewScheduleAction.user_id == user_id,
            ReviewScheduleAction.idempotency_key == idempotency_key,
        ))).scalar_one_or_none()
        if prior:
            if prior.action != "defer" or prior.payload != {"hours": hours, "schedule_id": schedule_id}:
                raise LearningHubError("IDEMPOTENCY_CONFLICT", "幂等键已用于不同操作")
            return prior.result
        row = (await db.execute(select(ReviewSchedule).where(
            ReviewSchedule.id == schedule_id, ReviewSchedule.user_id == user_id
        ))).scalar_one_or_none()
        if row is None:
            raise LearningHubError("REVIEW_NOT_FOUND", "复习计划不存在")
        row.deferred_until = datetime.now(timezone.utc) + timedelta(hours=hours)
        result = _schedule_payload(row)
        db.add(ReviewScheduleAction(
            user_id=user_id, schedule_id=row.id, idempotency_key=idempotency_key,
            action="defer", payload={"hours": hours, "schedule_id": schedule_id}, result=result,
        ))
        await db.flush()
        return result


async def complete_review(user_id: str, schedule_id: int, *, attempt_id: str, idempotency_key: str) -> dict[str, Any]:
    """Accept completion only when backed by a real submitted attempt."""
    async with get_db_session() as db:
        prior = (await db.execute(select(ReviewScheduleAction).where(
            ReviewScheduleAction.user_id == user_id,
            ReviewScheduleAction.idempotency_key == idempotency_key,
        ))).scalar_one_or_none()
        if prior:
            if prior.action != "complete" or prior.payload != {"attempt_id": attempt_id, "schedule_id": schedule_id}:
                raise LearningHubError("IDEMPOTENCY_CONFLICT", "幂等键已用于不同操作")
            return prior.result
        row = (await db.execute(select(ReviewSchedule).where(
            ReviewSchedule.id == schedule_id, ReviewSchedule.user_id == user_id
        ))).scalar_one_or_none()
        attempt = (await db.execute(select(PracticeAttempt).where(
            PracticeAttempt.id == attempt_id, PracticeAttempt.user_id == user_id
        ))).scalar_one_or_none()
        if row is None:
            raise LearningHubError("REVIEW_NOT_FOUND", "复习计划不存在")
        codes = (attempt.grading_snapshot or {}).get("knowledge_point_codes") if attempt else []
        if attempt is None or row.knowledge_point_code not in (codes or []):
            raise LearningHubError("ATTEMPT_EVIDENCE_REQUIRED", "完成复习必须提供该知识点的真实作答")
        # Projection refresh runs after an attempt is committed and therefore can
        # make ``updated_at`` newer than that same attempt.  When the projection
        # explicitly records it as the latest evidence, it is not stale.
        if _utc(attempt.submitted_at) < _utc(row.updated_at) and row.last_attempt_id != attempt.id:
            raise LearningHubError("STALE_ATTEMPT", "该作答早于本轮复习计划")
        old_stage = row.stage
        row.review_count += 1
        row.last_reviewed_at = _utc(attempt.submitted_at)
        row.deferred_until = None
        row.stage = min(old_stage + 1, len(SPACED_INTERVALS) - 1) if attempt.correct else 0
        row.interval_days = SPACED_INTERVALS[row.stage]
        row.consecutive_correct = row.consecutive_correct + 1 if attempt.correct else 0
        row.due_at = _utc(attempt.submitted_at) + timedelta(days=row.interval_days)
        row.last_attempt_id = attempt.id
        result = _schedule_payload(row)
        db.add(ReviewScheduleAction(
            user_id=user_id, schedule_id=row.id, idempotency_key=idempotency_key,
            action="complete", payload={"attempt_id": attempt_id, "schedule_id": schedule_id}, result=result,
        ))
        await db.flush()
        return result


async def today_hub(user_id: str, *, limit: int = 5) -> dict[str, Any]:
    """Build a bounded, explainable task list without LLM/Qdrant."""
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        states = sorted(await read_learning_states(db, user_id), key=lambda s: (s.mastery, s.confidence, s.knowledge_point_code))
        schedules = list((await db.execute(select(ReviewSchedule).where(
            ReviewSchedule.user_id == user_id,
            ReviewSchedule.due_at <= now,
            or_(ReviewSchedule.deferred_until.is_(None), ReviewSchedule.deferred_until <= now),
        ).order_by(ReviewSchedule.due_at))).scalars())
        codes = sorted({s.knowledge_point_code for s in states} | {s.knowledge_point_code for s in schedules})
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.code.in_(codes or ["__none__"])))).scalars())
        names = {point.code: point.name for point in points}
        pool_rows = (await db.execute(
            select(KnowledgePoint.code, func.count(Question.id))
            .join(QuestionKnowledgePoint, QuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
            .join(Question, Question.id == QuestionKnowledgePoint.question_id)
            .where(Question.review_status == "published", Question.practice_eligible.is_(True), Question.grading_mode == "deterministic")
            .group_by(KnowledgePoint.code)
        )).all()
        pool = dict(pool_rows)

    tasks: list[dict[str, Any]] = []
    used: set[str] = set()
    def add(kind: str, code: str, evidence: list[dict[str, Any]], priority: int) -> None:
        if code in used or len(tasks) >= limit:
            return
        count = int(pool.get(code, 0))
        tasks.append({
            "id": f"{kind}:{code}", "type": kind, "title": f"{names.get(code, code)}",
            "target_knowledge_point": {"code": code, "name": names.get(code, code)},
            "reason": "；".join(item["text"] for item in evidence), "evidence": evidence,
            "estimated_minutes": 12 if kind == "review" else 15,
            "priority": priority, "available_question_count": count,
            "start": {"route": "/apply/practice", "query": {"knowledge_point": code}} if count else None,
            "degradation": None if count else {"code": "QUESTION_POOL_EMPTY", "message": "该知识点暂无可用正式题目，请先复习讲义或选择其他任务"},
        })
        used.add(code)

    for row in schedules:
        add("review", row.knowledge_point_code, [{"type": "due_review", "text": f"复习已到期，当前间隔 {row.interval_days} 天", "value": row.due_at.isoformat()}], 100)
    for state in states:
        add("weakness", state.knowledge_point_code, [
            {"type": "mastery", "text": f"掌握度 {round(state.mastery * 100)}%", "value": state.mastery, **state_evidence(state)},
            {"type": "attempts", "text": f"来自 {state.attempts_count} 次真实作答", "value": state.attempts_count},
        ], 80)
    cold_start = not states
    if cold_start:
        tasks.append({
            "id": "diagnostic:start", "type": "diagnostic", "title": "完成基础诊断",
            "target_knowledge_point": None, "reason": "还没有足够学习证据，先用基础诊断了解你的起点",
            "evidence": [{"type": "cold_start", "text": "当前没有已完成作答", "value": 0}],
            "estimated_minutes": 15, "priority": 100, "available_question_count": sum(pool.values()),
            "start": {"route": "/apply/assessment", "query": {}} if sum(pool.values()) else None,
            "degradation": None if sum(pool.values()) else {"code": "QUESTION_POOL_EMPTY", "message": "正式题库暂不可用，请联系管理员发布题目"},
        })
    return {"generated_at": now, "algorithm_version": RECOMMENDATION_VERSION, "cold_start": cold_start, "primary": tasks[0] if tasks else None, "alternatives": tasks[1:limit]}


def _metric(value: Any, *, sample_size: int, period: str, now: datetime, status: str | None = None) -> dict[str, Any]:
    return {
        "value": value, "status": status or ("available" if sample_size else "insufficient_data"),
        "sample_size": sample_size, "period": period,
        "calculation_version": "learning-facts-v1", "updated_at": now,
    }


async def unified_dashboard(user_id: str, *, period: str = "7d") -> dict[str, Any]:
    days = {"7d": 7, "30d": 30, "90d": 90}[period]
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    hub = await today_hub(user_id)
    async with get_db_session() as db:
        states = sorted(await read_learning_states(db, user_id), key=lambda s: (s.mastery, s.knowledge_point_code))
        attempts = list((await db.execute(select(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id, PracticeAttempt.submitted_at >= start,
        ).order_by(PracticeAttempt.submitted_at))).scalars())
        activities = list((await db.execute(select(LearningActivitySession).where(
            LearningActivitySession.user_id == user_id, LearningActivitySession.started_at >= start,
        ))).scalars())
        points = list((await db.execute(select(KnowledgePoint, Chapter).join(Chapter, Chapter.id == KnowledgePoint.chapter_id).where(
            KnowledgePoint.code.in_([s.knowledge_point_code for s in states] or ["__none__"])
        ))).all())
    names = {point.code: point.name for point, _ in points}
    chapter_names = {point.code: chapter.name for point, chapter in points}
    daily = {(start + timedelta(days=i)).date().isoformat(): {"attempts": 0, "correct": 0, "active_seconds": 0} for i in range(days)}
    for attempt in attempts:
        key = _utc(attempt.submitted_at).date().isoformat()
        if key in daily:
            daily[key]["attempts"] += 1
            daily[key]["correct"] += int(attempt.correct)
    for activity in activities:
        key = _utc(activity.started_at).date().isoformat()
        if key in daily:
            daily[key]["active_seconds"] += int(activity.active_seconds or 0)
    total_correct = sum(int(a.correct) for a in attempts)
    active_seconds = sum(int(a.active_seconds or 0) for a in activities)
    study_days = sum(1 for item in daily.values() if item["attempts"] or item["active_seconds"])
    trend = [{"date": date, **values, "accuracy": round(values["correct"] / values["attempts"] * 100) if values["attempts"] else None} for date, values in daily.items()]
    chapter_stats: dict[str, list[float]] = {}
    for state in states:
        chapter_stats.setdefault(chapter_names.get(state.knowledge_point_code, "未归属章节"), []).append(state.mastery)
    chapter_mastery = []
    for name, values in chapter_stats.items():
        count = sum(s.attempts_count for s in states if chapter_names.get(s.knowledge_point_code, "未归属章节") == name)
        chapter_mastery.append({"name": name, "value": round(sum(values) / len(values), 4),
                                "sample_size": len(values), **evidence_summary(sum(values) / len(values), count)})
    cold = not states
    weak = states[:3]
    strong = list(reversed(states[-3:])) if states else []
    return {
        "generated_at": now, "state_version": states[0].calculation_version if states else "uks-rules-v1",
        "period": period,
        "status": "learning" if states else "discovering", "status_message": "正在根据真实作答了解你" if cold else "画像来自最近的真实作答",
        "progress": {"attempts": sum(s.attempts_count for s in states), "correct": sum(s.correct_count for s in states), "knowledge_points": len(states)},
        "dimensions": {
            "mastery": [{"code": s.knowledge_point_code, "value": s.mastery, **state_evidence(s)} for s in states],
            "memory_strength": [{"code": s.knowledge_point_code, "value": s.memory_strength} for s in states],
            "transfer": [{"code": s.knowledge_point_code, "value": s.variant_performance, "attempts": s.variant_attempts_count} for s in states],
            "error_patterns": {k: sum((s.error_type_counts or {}).get(k, 0) for s in states) for k in sorted({k for s in states for k in (s.error_type_counts or {})})},
        },
        "weakest": [{"code": s.knowledge_point_code, "name": names.get(s.knowledge_point_code, s.knowledge_point_code), "mastery": s.mastery, "confidence": s.confidence, "sample_size": s.attempts_count, **state_evidence(s)} for s in weak],
        "strongest": [{"code": s.knowledge_point_code, "name": names.get(s.knowledge_point_code, s.knowledge_point_code), "mastery": s.mastery, "confidence": s.confidence, "sample_size": s.attempts_count, **state_evidence(s)} for s in strong],
        "metrics": {
            "active_seconds": _metric(active_seconds, sample_size=len(activities), period=period, now=now),
            "study_days": _metric(study_days, sample_size=len(activities) + len(attempts), period=period, now=now),
            "attempts": _metric(len(attempts), sample_size=len(attempts), period=period, now=now),
            "correct": _metric(total_correct, sample_size=len(attempts), period=period, now=now),
            "accuracy": _metric(round(total_correct / len(attempts) * 100) if attempts else None, sample_size=len(attempts), period=period, now=now),
        },
        "trend": trend,
        "heatmap": [{"date": item["date"], "active_seconds": item["active_seconds"], "attempts": item["attempts"]} for item in trend],
        "chapter_mastery": chapter_mastery,
        "goals": {"status": "not_configured", "items": [], "message": "尚未设置学习目标"},
        "data_quality": {"status": "complete", "sources": ["practice_attempts", "learning_activity_sessions", "user_knowledge_states"], "message": "仅统计服务端已确认的学习事实"},
        "today": hub,
    }


async def unified_profile(user_id: str) -> dict[str, Any]:
    dashboard = await unified_dashboard(user_id, period="90d")
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        attempts = list((await db.execute(select(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id,
        ).order_by(PracticeAttempt.submitted_at))).scalars())
        schedules = list((await db.execute(select(ReviewSchedule).where(
            ReviewSchedule.user_id == user_id,
        ).order_by(ReviewSchedule.due_at))).scalars())
    interval_evidence = []
    for attempt in attempts:
        signals = (attempt.grading_snapshot or {}).get("learning_signals") or {}
        interval = signals.get("review_interval_days")
        if attempt.correct and interval is not None:
            interval_evidence.append({"attempt_id": attempt.id, "interval_days": int(interval), "retained": True, "observed_at": attempt.submitted_at})
    distinct_intervals = sorted({item["interval_days"] for item in interval_evidence})
    span_days = 0
    if len(interval_evidence) >= 2:
        span_days = (_utc(interval_evidence[-1]["observed_at"]) - _utc(interval_evidence[0]["observed_at"])).days
    curve_ready = len(distinct_intervals) >= 3 and span_days >= 7
    insights = []
    attempts_metric = dashboard["metrics"]["attempts"]
    if attempts_metric["sample_size"]:
        accuracy = dashboard["metrics"]["accuracy"]["value"]
        insights.append({
            "title": "近期作答表现", "conclusion": f"近 90 天正确率为 {accuracy}%",
            "evidence": {"metric": "accuracy", "value": accuracy, "sample_size": attempts_metric["sample_size"], "period": "90d"},
            "confidence": min(1.0, attempts_metric["sample_size"] / 20),
            "action": {"label": "查看薄弱点", "route": "/dashboard"},
        })
    return {
        "generated_at": now, "status": dashboard["status"], "status_message": dashboard["status_message"],
        "dimensions": dashboard["dimensions"], "review_plan": [_schedule_payload(s) for s in schedules],
        "forgetting_curve": {
            "status": "available" if curve_ready else "collecting", "observations": interval_evidence if curve_ready else [],
            "sample_size": len(interval_evidence), "distinct_intervals": len(distinct_intervals), "span_days": span_days,
            "required": {"distinct_intervals": 3, "span_days": 7}, "algorithm_version": "observed-retention-v1",
            "message": "已达到个人曲线展示门槛" if curve_ready else "需要至少 3 个不同复习间隔且跨越 7 天的真实正确复习证据",
        },
        "insights": insights,
        "data_quality": dashboard["data_quality"],
    }
