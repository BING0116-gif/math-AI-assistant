"""Deterministic learner-state projections sourced only from canonical attempts."""
from __future__ import annotations

import logging
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from app.data.database import get_db_session
from app.data.models import PracticeAttempt, ReviewSchedule, UserKnowledgeState
from app.config.settings import settings
from app.services.mastery_evidence import evidence_summary, unique_evidence

logger = logging.getLogger(__name__)
CALCULATION_VERSION = "uks-evidence-v2"


def policy_version() -> str:
    """配置变动也使派生快照失效，避免旧 cap 长期滞留。"""
    policy = json.dumps([settings.MASTERY_CONFIDENCE_CAP, settings.MASTERY_CONFIDENCE_LEVELS], sort_keys=True)
    return f"{CALCULATION_VERSION}-{hashlib.sha256(policy.encode()).hexdigest()[:8]}"


def state_evidence(state) -> dict:
    return evidence_summary(state.mastery, state.attempts_count)


def _aware(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _signals(attempt: PracticeAttempt) -> dict[str, Any]:
    return (attempt.grading_snapshot or {}).get("learning_signals") or {}


def _kind(attempt: PracticeAttempt) -> str:
    return str(_signals(attempt).get("attempt_kind") or "regular")


def _calculate_state(rows: list[PracticeAttempt]) -> dict[str, Any]:
    """Fold immutable attempts in stable order into one explainable state."""
    rows = sorted(unique_evidence(rows, attempts=True), key=lambda row: (_aware(row.submitted_at), row.id))
    if not rows:
        raise ValueError("没有有效独立答题证据，不能生成掌握度投影")
    mastery = 0.2
    error_counts: Counter[str] = Counter()
    history: list[dict[str, Any]] = []
    correct_count = variant_attempts = variant_correct = streak = 0
    last_reviewed_at = None

    for attempt in rows:
        snapshot, signals, kind = attempt.grading_snapshot or {}, _signals(attempt), _kind(attempt)
        difficulty = max(1, min(5, int(snapshot.get("difficulty") or 3)))
        weight = 0.8 + difficulty * 0.1
        if kind == "original_retry":
            weight *= 0.8
        elif kind == "variant":
            weight *= 1.25
            variant_attempts += 1
        elif kind == "spaced_review":
            interval_days = max(1, int(signals.get("review_interval_days") or 1))
            weight *= min(1.7, 1.3 + interval_days * 0.04)
        if signals.get("hint_used"):
            weight *= 0.75
        if signals.get("solution_viewed"):
            weight *= 0.6
        spent = signals.get("time_spent_seconds")
        expected = snapshot.get("estimated_time")
        if spent is not None and expected:
            ratio = float(spent) / max(1.0, float(expected))
            if ratio < 0.2 or ratio > 3.0:
                weight *= 0.9

        before = mastery
        if attempt.correct:
            correct_count += 1
            streak += 1
            variant_correct += int(kind == "variant")
            mastery += (1.0 - mastery) * 0.22 * weight
            if not history:
                mastery = min(mastery, 0.49)
        else:
            streak = 0
            mastery -= mastery * 0.28 * weight
            error_counts[str(snapshot.get("error_category") or "UNKNOWN")] += 1

        mastery = round(max(0.0, min(0.98, mastery)), 6)
        submitted_at = _aware(attempt.submitted_at)
        if kind in {"original_retry", "variant", "spaced_review"}:
            last_reviewed_at = submitted_at
        history.append({
            "attempt_id": attempt.id, "at": submitted_at.isoformat(), "kind": kind,
            "correct": bool(attempt.correct), "weight": round(weight, 4),
            "time_spent_seconds": spent,
            "mastery_before": round(before, 6), "mastery_after": mastery,
            "reason": "correct_evidence" if attempt.correct else "incorrect_evidence",
            "version": CALCULATION_VERSION,
        })

    last, last_time = rows[-1], _aware(rows[-1].submitted_at)
    variant_performance = variant_correct / variant_attempts if variant_attempts else 0.0
    evidence_kinds = len({_kind(row) for row in rows if row.correct})
    confidence = min(0.98, 0.12 + len(rows) * 0.1 + evidence_kinds * 0.08)
    if len(rows) < 2:
        confidence = min(confidence, 0.3)
    interval = 1 if not last.correct else min(30, 2 ** max(0, streak - 1))
    if _kind(last) == "variant" and last.correct:
        interval = max(interval, 3)
    if _kind(last) == "spaced_review" and last.correct:
        interval = max(interval, min(30, int(_signals(last).get("review_interval_days") or 1) * 2))
    summary = evidence_summary(mastery, len(rows))
    mastery = summary["mastery_score"]
    memory_strength = min(0.98, mastery * (0.75 + min(interval, 14) / 56))
    next_review_at = last_time + timedelta(days=interval)
    return {
        "attempts_count": len(rows), "correct_count": correct_count,
        "mastery": round(mastery, 4), "memory_strength": round(memory_strength, 4),
        "confidence": round(confidence, 4), "mistake_count": len(rows) - correct_count,
        "error_type_counts": dict(sorted(error_counts.items())),
        "variant_attempts_count": variant_attempts, "variant_correct_count": variant_correct,
        "variant_performance": round(variant_performance, 4), "last_attempt_id": last.id,
        "last_practiced_at": last_time, "last_reviewed_at": last_reviewed_at,
        "next_review_at": next_review_at, "calculation_version": policy_version(),
        "calculation_reason": {"rule": CALCULATION_VERSION, **summary, "latest_attempt_kind": _kind(last), "latest_correct": bool(last.correct), "latest_weight": history[-1]["weight"]},
        "evolution_history": history, "interval_days": interval, "consecutive_correct": streak,
    }


async def rebuild_learning_projections_in_session(db, user_id: str) -> dict[str, int]:
    """Rebuild state and review schedules in the caller's transaction."""
    attempts = list((await db.execute(
            select(PracticeAttempt).where(PracticeAttempt.user_id == user_id)
            .order_by(PracticeAttempt.submitted_at, PracticeAttempt.id)
    )).scalars())
    grouped: dict[str, list[PracticeAttempt]] = defaultdict(list)
    for attempt in unique_evidence(attempts, attempts=True):
        for code in set((attempt.grading_snapshot or {}).get("knowledge_point_codes") or []):
            grouped[str(code)].append(attempt)

    existing_schedules = {
        row.knowledge_point_code: row for row in (await db.execute(
            select(ReviewSchedule).where(ReviewSchedule.user_id == user_id)
        )).scalars()
    }
    await db.execute(delete(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id))
    for code, rows in sorted(grouped.items()):
        state = _calculate_state(rows)
        db.add(UserKnowledgeState(
            user_id=user_id, knowledge_point_code=code,
            **{key: value for key, value in state.items() if key not in {"interval_days", "consecutive_correct"}},
        ))
        schedule = existing_schedules.pop(code, None)
        if schedule is None:
            schedule = ReviewSchedule(user_id=user_id, knowledge_point_code=code)
            db.add(schedule)
        schedule.due_at = state["next_review_at"]
        schedule.interval_days = state["interval_days"]
        schedule.consecutive_correct = state["consecutive_correct"]
        schedule.last_attempt_id = state["last_attempt_id"]
        schedule.stage = min(3, max(0, state["consecutive_correct"] - 1))
        schedule.algorithm_version = "spaced-review-v1"
        schedule.last_reviewed_at = state["last_reviewed_at"]
    for obsolete in existing_schedules.values():
        await db.delete(obsolete)
    return {"knowledge_states": len(grouped), "review_schedules": len(grouped), "new_error_items": 0}


async def read_learning_states(db, user_id: str) -> list[UserKnowledgeState]:
    """读取当前证据策略的状态；旧投影只读重算，不改写学生历史/复习排期。"""
    states = list((await db.execute(select(UserKnowledgeState).where(
        UserKnowledgeState.user_id == user_id,
    ))).scalars())
    if states and all(state.calculation_version == policy_version() for state in states):
        return states
    attempts = list((await db.execute(select(PracticeAttempt).where(
        PracticeAttempt.user_id == user_id,
    ).order_by(PracticeAttempt.submitted_at, PracticeAttempt.id))).scalars())
    grouped = defaultdict(list)
    for attempt in unique_evidence(attempts, attempts=True):
        for code in set((attempt.grading_snapshot or {}).get("knowledge_point_codes") or []):
            grouped[str(code)].append(attempt)
    return [UserKnowledgeState(
        user_id=user_id, knowledge_point_code=code,
        **{key: value for key, value in _calculate_state(rows).items()
           if key not in {"interval_days", "consecutive_correct"}},
    ) for code, rows in sorted(grouped.items())]


async def rebuild_learning_projections(user_id: str) -> dict[str, int]:
    """Replace derived rows from immutable attempts; repeated runs are identical."""
    async with get_db_session() as db:
        return await rebuild_learning_projections_in_session(db, user_id)


async def refresh_learning_projections_safely(user_id: str) -> None:
    try:
        await rebuild_learning_projections(user_id)
        from app.services.skill_aggregator import SkillAggregator
        await SkillAggregator().recalculate_skills(user_id)
    except Exception:
        logger.exception("Learning projection refresh failed; source attempts remain committed", extra={"user_id": user_id})
