"""Owner-scoped learning-map projection for the published course catalog."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import (
    Course,
    ErrorItem,
    KnowledgeGraphVersion,
    KnowledgePoint,
    ReviewSchedule,
)
from app.services.learning_projection import read_learning_states, state_evidence


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _base_status(mastery: float, attempts: int) -> str:
    if attempts <= 0:
        return "unlearned"
    if mastery >= 0.85:
        return "mastered"
    if mastery < 0.30:
        return "weak"
    return "learning"


async def build_learning_map(session: AsyncSession, course_id: str, user_id: str) -> dict | None:
    """Build one deterministic, owner-scoped projection without mutating evidence."""
    course = await session.scalar(select(Course).where(Course.id == course_id, Course.status == "active"))
    if course is None or not course.default_version_id:
        return None
    version = await session.scalar(select(KnowledgeGraphVersion).where(
        KnowledgeGraphVersion.id == course.default_version_id,
        KnowledgeGraphVersion.course_id == course.id,
        KnowledgeGraphVersion.status == "published",
    ))
    if version is None:
        return None

    points = list((await session.execute(select(KnowledgePoint).where(
        KnowledgePoint.version_id == version.id,
        KnowledgePoint.status == "active",
    ).order_by(KnowledgePoint.sort_order, KnowledgePoint.code))).scalars())
    codes = {point.code for point in points}
    states = {
        state.knowledge_point_code: state
        for state in await read_learning_states(session, user_id)
        if state.knowledge_point_code in codes
    }
    schedules = list((await session.execute(select(ReviewSchedule).where(
        ReviewSchedule.user_id == user_id,
        ReviewSchedule.knowledge_point_code.in_(codes),
    ))).scalars()) if codes else []
    schedules_by_code = {row.knowledge_point_code: row for row in schedules}
    now = datetime.now(timezone.utc)

    errors = list((await session.execute(select(ErrorItem).where(
        ErrorItem.user_id == user_id,
        ErrorItem.is_mastered.is_(False),
        or_(ErrorItem.knowledge_point_codes.is_not(None), ErrorItem.categories.is_not(None)),
    ))).scalars())
    error_counts = {code: 0 for code in codes}
    due_error_counts = {code: 0 for code in codes}
    point_codes_by_label = {
        label: point.code
        for point in points
        for label in [point.code, point.name, *(point.aliases or [])]
        if label
    }
    for item in errors:
        raw_labels = [*(item.knowledge_point_codes or []), *(item.categories or [])]
        mapped = {point_codes_by_label[label] for label in raw_labels if label in point_codes_by_label}
        for code in mapped:
            error_counts[code] += 1
            if item.next_review_at and _aware(item.next_review_at) <= now:
                due_error_counts[code] += 1

    mastered_codes = {
        code for code, state in states.items()
        if state.attempts_count > 0 and state.mastery >= 0.85
    }
    point_rows = []
    for point in points:
        state = states.get(point.code)
        prerequisites = [code for code in (point.prerequisites or []) if code in codes]
        missing = [code for code in prerequisites if code not in mastered_codes]
        schedule = schedules_by_code.get(point.code)
        due_at = _aware(schedule.due_at) if schedule else None
        review_due = bool(due_at and due_at <= now and not (schedule.deferred_until and _aware(schedule.deferred_until) > now))
        attempts = state.attempts_count if state else 0
        mastery = state.mastery if state else 0.0
        status = "locked" if missing and attempts <= 0 else _base_status(mastery, attempts)
        point_rows.append({
            "id": point.id,
            "code": point.code,
            "status": status,
            "mastery": mastery,
            "attempts": attempts,
            "correct": state.correct_count if state else 0,
            "evidence": state_evidence(state) if state else {"evidence_count": 0, "confidence_level": "none"},
            "missing_prerequisites": missing,
            "review_due": review_due,
            "review_due_at": due_at,
            "review_schedule_id": schedule.id if review_due else None,
            "open_error_count": error_counts[point.code],
            "due_error_count": due_error_counts[point.code],
        })

    def recommendation_key(row: dict) -> tuple:
        # Due review first, then due/open errors, weak evidence, active learning,
        # and finally the earliest unlocked new point.
        status_rank = {"weak": 0, "learning": 1, "unlearned": 2, "mastered": 3, "locked": 4}
        return (
            0 if row["review_due"] else 1,
            0 if row["due_error_count"] else 1,
            0 if row["open_error_count"] else 1,
            status_rank[row["status"]],
            next((point.sort_order for point in points if point.code == row["code"]), 0),
        )

    candidates = [
        row for row in point_rows
        if row["status"] != "locked" and (row["status"] != "mastered" or row["review_due"] or row["due_error_count"])
    ]
    candidates.sort(key=recommendation_key)

    def describe(row: dict) -> tuple[str, str]:
        if row["review_due"]:
            return "DUE_REVIEW", "这项复习已经到期，先巩固可减少遗忘。"
        if row["due_error_count"]:
            return "DUE_ERROR_REVIEW", f"有 {row['due_error_count']} 道相关错题已到复习时间。"
        if row["open_error_count"]:
            return "OPEN_ERRORS", f"有 {row['open_error_count']} 道相关错题仍待巩固。"
        if row["status"] == "weak":
            return "WEAK_MASTERY", "已有作答证据显示这里较薄弱，建议优先补强。"
        if row["status"] == "learning":
            return "CONTINUE_LEARNING", "你已经开始学习，继续练习有助于形成稳定掌握。"
        return "NEXT_UNLOCKED", "前置条件已满足，可以从这里继续学习。"

    recommendations = []
    for index, row in enumerate(candidates[:3]):
        reason_code, reason = describe(row)
        recommendations.append({
            "knowledge_point_id": row["id"],
            "knowledge_point_code": row["code"],
            "rank": index + 1,
            "kind": "primary" if index == 0 else "secondary",
            "reason_code": reason_code,
            "reason": reason,
        })

    return {
        "course_id": course.id,
        "version_id": version.id,
        "generated_at": now,
        "points": point_rows,
        "primary_recommendation": recommendations[0] if recommendations else None,
        "secondary_recommendations": recommendations[1:3],
    }
