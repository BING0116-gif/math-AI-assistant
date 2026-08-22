"""Rebuildable learning projections sourced exclusively from PracticeAttempt."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.data.database import get_db_session
from app.data.models import ErrorItem, PracticeAttempt, ReviewSchedule, UserKnowledgeState

logger = logging.getLogger(__name__)


def classify_error(answer) -> str | None:
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        return "unanswered"
    return "answer_mismatch"


async def rebuild_learning_projections(user_id: str) -> dict[str, int]:
    """Idempotently rebuild one user's knowledge/review projections.

    This is intentionally callable after the main submission transaction. A
    projection failure never rolls back an accepted attempt and can be repaired
    by calling this function again.
    """
    async with get_db_session() as db:
        attempts = list((await db.execute(
            select(PracticeAttempt).where(PracticeAttempt.user_id == user_id)
            .order_by(PracticeAttempt.submitted_at, PracticeAttempt.id)
        )).scalars())
        grouped = defaultdict(list)
        for attempt in attempts:
            for code in (attempt.grading_snapshot or {}).get("knowledge_point_codes") or []:
                grouped[str(code)].append(attempt)

        await db.execute(delete(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id))
        await db.execute(delete(ReviewSchedule).where(ReviewSchedule.user_id == user_id))
        now = datetime.now(timezone.utc)
        for code, rows in grouped.items():
            correct_count = sum(int(row.correct) for row in rows)
            last = rows[-1]
            streak = 0
            for row in reversed(rows):
                if not row.correct:
                    break
                streak += 1
            interval = min(30, 2 ** max(0, streak - 1)) if last.correct else 1
            base_time = last.submitted_at or now
            if base_time.tzinfo is None:
                base_time = base_time.replace(tzinfo=timezone.utc)
            db.add(UserKnowledgeState(
                user_id=user_id, knowledge_point_code=code,
                attempts_count=len(rows), correct_count=correct_count,
                mastery=round(correct_count / len(rows), 4),
                last_attempt_id=last.id, last_practiced_at=base_time,
            ))
            db.add(ReviewSchedule(
                user_id=user_id, knowledge_point_code=code,
                due_at=base_time + timedelta(days=interval), interval_days=interval,
                consecutive_correct=streak, last_attempt_id=last.id,
            ))

        wrong_attempt_ids = {row.id for row in attempts if not row.correct}
        existing = list((await db.execute(select(ErrorItem).where(
            ErrorItem.user_id == user_id, ErrorItem.item_id.in_(wrong_attempt_ids or {"__none__"})
        ))).scalars())
        existing_ids = {item.item_id for item in existing}
        for attempt in attempts:
            if attempt.correct or attempt.id in existing_ids:
                continue
            snap = attempt.grading_snapshot or {}
            db.add(ErrorItem(
                user_id=user_id, item_id=attempt.id,
                question=snap.get("question_content") or f"题目 {attempt.question_id}",
                question_type="practice_attempt",
                error_reason=classify_error(attempt.user_answer) or "answer_mismatch",
                categories=snap.get("knowledge_point_codes") or [],
                original_answer=str(attempt.user_answer or ""),
                correct_answer=str(snap.get("correct_answer") or ""),
                added_at=(attempt.submitted_at or now).isoformat(),
            ))
        return {"knowledge_states": len(grouped), "review_schedules": len(grouped), "new_error_items": len(wrong_attempt_ids - existing_ids)}


async def refresh_learning_projections_safely(user_id: str) -> None:
    try:
        await rebuild_learning_projections(user_id)
    except Exception:
        logger.exception("Learning projection refresh failed; source attempts remain committed", extra={"user_id": user_id})
