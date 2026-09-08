"""掌握度证据边界；参与行为与自报结果不能证明独立答题能力。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from app.config.settings import settings


MASTERY_EVIDENCE_EVENT_TYPES = frozenset({
    "practice_answer", "assessment_answer", "exam_answer",
})
ENGAGEMENT_ONLY_EVENT_TYPES = frozenset({
    "problem_solving", "concept_inquiry", "error_analysis", "review", "casual_chat",
    "feedback", "error_recorded", "review_mastered", "ask", "skip",
    "answer_correct", "answer_wrong", "unknown",
})


class MasteryEvidenceSummary(BaseModel):
    mastery_score: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)
    confidence_level: str


def _value(record: Any, name: str, default=None):
    return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)


def _independent(answer: Any, result: Any, metadata: dict) -> bool:
    signals = metadata.get("learning_signals") or metadata
    return (
        type(result) is bool
        and answer is not None and answer != "" and answer != [] and answer != {}
        and (not isinstance(answer, str) or bool(answer.strip()))
        and not metadata.get("needs_review")
        and not signals.get("hint_used") and not signals.get("solution_viewed")
    )


def is_mastery_evidence(record) -> bool:
    """只接纳有题目、有独立答案且结果已确定的服务端答题事件。"""
    return (
        _value(record, "event_type") in MASTERY_EVIDENCE_EVENT_TYPES
        and bool(_value(record, "user_id")) and bool(_value(record, "question_id"))
        and not _value(record, "hint_count", 0)
        and _independent(_value(record, "user_answer"), _value(record, "is_correct"),
                         _value(record, "metadata_", {}) or {})
    )


def is_attempt_evidence(attempt) -> bool:
    """PracticeAttempt 是三类正式答题事件共享的 SQL 真值，不再叠加其流水副本。"""
    return (
        bool(_value(attempt, "user_id")) and bool(_value(attempt, "question_id"))
        and _independent(_value(attempt, "user_answer"), _value(attempt, "correct"),
                         _value(attempt, "grading_snapshot", {}) or {})
    )


def unique_evidence(records: Iterable, *, attempts: bool = False) -> list:
    """按 owner + 持久化事件标识去重；同一题的不同正式提交仍是不同证据。"""
    seen, result, owners = set(), [], set()
    for record in records:
        if not (is_attempt_evidence(record) if attempts else is_mastery_evidence(record)):
            continue
        owner = _value(record, "user_id")
        owners.add(owner)
        if len(owners) > 1:
            raise ValueError("掌握度聚合不能混合不同用户的证据")
        metadata = _value(record, "metadata_", {}) or {}
        identifier = metadata.get("attempt_id") or metadata.get("event_id")
        if not identifier and metadata.get("session_id"):
            identifier = (metadata["session_id"], _value(record, "question_id"))
        identifier = identifier or _value(record, "id") or _value(record, "event_id")
        if not identifier:
            continue  # 没有稳定身份的事件不能作为可审计证据。
        key = (owner, identifier)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def evidence_summary(score: float, count: int) -> dict:
    """只在算法最终输出施加置信度上限，不修改原权重。"""
    level = next(name for name, (low, high) in settings.MASTERY_CONFIDENCE_LEVELS.items()
                 if count >= low and (high is None or count <= high))
    capped = min(score, settings.MASTERY_CONFIDENCE_CAP.get(count, 1.0)) if count else 0.0
    return MasteryEvidenceSummary(
        mastery_score=max(0.0, min(1.0, capped)), evidence_count=count, confidence_level=level,
    ).model_dump()


def compute_mastery_evidence(records) -> tuple[float, int, str]:
    """LearningRecord 兼容聚合，复用既有时间衰减/难度加权函数。"""
    from app.services.skill_aggregator import SkillAggregator

    rows = unique_evidence(records)
    now = datetime.now(timezone.utc)
    rows.sort(key=lambda r: (SkillAggregator._parse_datetime(_value(r, "created_at")) or now,
                             str(_value(r, "id", ""))), reverse=True)
    weighted = [(_value(r, "is_correct"), _value(r, "difficulty"),
                 _value(r, "time_spent"), _value(r, "created_at")) for r in rows]
    raw, *_ = SkillAggregator()._calculate_mastery(weighted, now)
    summary = evidence_summary(raw, len(rows))
    return summary["mastery_score"], summary["evidence_count"], summary["confidence_level"]
