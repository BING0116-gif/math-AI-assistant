"""Transactional error-book aggregation and evidence-based review state machine."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import ErrorItem, ErrorReviewEvent, PracticeAttempt
from app.services.review_scheduler import schedule_after_review, schedule_new_error

STATES = ("new", "understanding", "consolidating", "mastered")
EVENTS = ("original_correct", "variant_correct", "spaced_correct")


async def capture_wrong_attempt(
    db: AsyncSession,
    *,
    attempt: PracticeAttempt,
    question_snapshot: dict[str, Any],
    classification: dict[str, Any] | None,
) -> ErrorItem:
    """Aggregate one wrong attempt while retaining the immutable attempt fact."""
    await db.flush()
    item = (await db.execute(
        select(ErrorItem).where(
            ErrorItem.user_id == attempt.user_id,
            ErrorItem.question_id == attempt.question_id,
        ).with_for_update()
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    answer = attempt.user_answer
    if not isinstance(answer, str):
        import json
        answer = json.dumps(answer, ensure_ascii=False)
    if item is None:
        item = ErrorItem(
            user_id=attempt.user_id,
            item_id=str(uuid.uuid4()),
            question_id=attempt.question_id,
            question=question_snapshot.get("content") or "",
            question_type=question_snapshot.get("question_type") or "text",
            error_reason=(classification or {}).get("reason") or "答题错误",
            categories=list(question_snapshot.get("knowledge_point_codes") or []),
            knowledge_point_codes=list(question_snapshot.get("knowledge_point_codes") or []),
            original_answer=answer or "",
            correct_answer=str((attempt.grading_snapshot or {}).get("correct_answer") or ""),
            added_at=now.isoformat(),
            source="attempt",
            structure_confidence=float((classification or {}).get("confidence") or 1.0),
            review_state="new",
            is_mastered=False,
            wrong_attempt_count=1,
            last_attempt_id=attempt.id,
        )
        db.add(item)
        await db.flush()
    else:
        item.wrong_attempt_count = (item.wrong_attempt_count or 0) + 1
        item.last_attempt_id = attempt.id
        item.original_answer = answer or item.original_answer
        item.error_reason = (classification or {}).get("reason") or item.error_reason
        item.review_state = "new"
        item.is_mastered = False
    # T02：无论新错还是再错，都（重）置错题级复习排期——答错回到最短间隔并置顶，
    # 练习答错后自动进入明确的首次复习排期，不再依赖前端兜底。
    schedule_new_error(item, now=now)
    event_id = f"wrong_attempt:{attempt.id}"
    exists = await db.scalar(select(ErrorReviewEvent.id).where(ErrorReviewEvent.event_id == event_id))
    if not exists:
        db.add(ErrorReviewEvent(
            event_id=event_id, error_item_id=item.id, user_id=attempt.user_id,
            attempt_id=attempt.id, event_type="wrong_attempt", from_state=item.review_state,
            to_state="new", details={"question_id": attempt.question_id}, created_at=now,
        ))
    return item


async def record_review_evidence(
    db: AsyncSession, *, user_id: str, item_id: str, event_type: str,
    event_id: str, attempt_id: str | None = None, details: dict[str, Any] | None = None,
) -> ErrorItem:
    if event_type not in EVENTS:
        raise ValueError("unsupported review event")
    existing = await db.scalar(select(ErrorReviewEvent.id).where(ErrorReviewEvent.event_id == event_id))
    item = (await db.execute(select(ErrorItem).where(
        ErrorItem.user_id == user_id, ErrorItem.item_id == item_id,
    ).with_for_update())).scalar_one_or_none()
    if item is None:
        raise LookupError("error item not found")
    if existing:
        return item
    prior = set((await db.execute(select(ErrorReviewEvent.event_type).where(
        ErrorReviewEvent.user_id == user_id, ErrorReviewEvent.error_item_id == item.id,
    ))).scalars())
    old = item.review_state or "new"
    new = old
    if event_type == "original_correct":
        new = "understanding" if old == "new" else old
    elif event_type == "variant_correct" and "original_correct" in prior:
        new = "consolidating" if old != "mastered" else old
    elif event_type == "spaced_correct" and {"original_correct", "variant_correct"}.issubset(prior):
        new = "mastered"
    item.review_state = new
    item.is_mastered = new == "mastered"
    item.last_reviewed_at = datetime.now(timezone.utc)
    # T02：复习事件非重放（上方 existing 检查已返回）才走到这里，因此同一 attempt
    # 重放不会重复推进状态，也不会重复延后排期（幂等复用 event_id 唯一约束）。
    schedule_after_review(item, correct=True, now=datetime.now(timezone.utc))
    details = dict(details or {})
    details["review_interval_days"] = item.review_interval_days
    details["review_streak"] = item.review_streak
    details["next_review_at"] = item.next_review_at.isoformat() if item.next_review_at else None
    db.add(ErrorReviewEvent(
        event_id=event_id, error_item_id=item.id, user_id=user_id, attempt_id=attempt_id,
        event_type=event_type, from_state=old, to_state=new, details=details or {},
    ))
    return item
