"""T01 · Mastery 证据分层 + 置信度上限 的回归测试。

不依赖数据库：直接对 app.services.mastery_evidence 的纯函数做单元验证，
并复用既有的 SkillAggregator._calculate_mastery（时间/难度加权算法）确认只加 cap、未重写。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import mastery_evidence as me
from app.services.mastery_evidence import (
    MASTERY_EVIDENCE_EVENT_TYPES,
    ENGAGEMENT_ONLY_EVENT_TYPES,
    compute_mastery_evidence,
    evidence_summary,
    is_mastery_evidence,
    unique_evidence,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rec(
    event_type: str = "practice_answer",
    *,
    user_id: str = "u1",
    question_id: str = "q1",
    user_answer: str = "x=1",
    is_correct: bool = True,
    hint_count: int = 0,
    metadata_: dict | None = None,
    rid: str = "r1",
    created_at=None,
    difficulty: int = 3,
    time_spent: int = 10,
) -> dict:
    """构造一条可被 is_mastery_evidence 识别的独立答题证据记录（dict 形态）。"""
    return {
        "event_type": event_type,
        "user_id": user_id,
        "question_id": question_id,
        "user_answer": user_answer,
        "is_correct": is_correct,
        "hint_count": hint_count,
        "metadata_": metadata_ or {"attempt_id": rid},
        "id": rid,
        "created_at": created_at or _now(),
        "difficulty": difficulty,
        "time_spent": time_spent,
    }


# ---- 事件分类 ----
def test_mastery_evidence_event_types_are_real_answer_events():
    # 由代码实测确认的三类独立答题事件
    assert MASTERY_EVIDENCE_EVENT_TYPES == frozenset(
        {"practice_answer", "assessment_answer", "exam_answer"}
    )


def test_engagement_event_is_not_mastery_evidence():
    for et in ("ask", "view_explanation", "problem_solving", "concept_inquiry", "review", "casual_chat"):
        assert not is_mastery_evidence(_rec(event_type=et)), f"{et} 不应被计为掌握度证据"


def test_hint_assisted_answer_is_not_mastery_evidence():
    # 看了提示/解析的独立作答不应算证据（这正是"伪证据"来源）
    with_hint = _rec(metadata_={"attempt_id": "a1", "learning_signals": {"hint_used": True}})
    with_solution = _rec(metadata_={"attempt_id": "a1", "learning_signals": {"solution_viewed": True}})
    assert not is_mastery_evidence(with_hint)
    assert not is_mastery_evidence(with_solution)


# ---- 置信度上限：evidence_summary 直接验证 ----
def test_evidence_summary_caps_single_and_double_evidence():
    assert evidence_summary(0.95, 1) == {
        "mastery_score": 0.5, "evidence_count": 1, "confidence_level": "low",
    }
    assert evidence_summary(0.95, 2) == {
        "mastery_score": 0.8, "evidence_count": 2, "confidence_level": "medium",
    }


def test_evidence_summary_no_cap_from_three_evidence_onward():
    # 3 条及以上不再按 MASTERY_CONFIDENCE_CAP 限制
    assert evidence_summary(0.95, 3)["mastery_score"] == 0.95
    assert evidence_summary(0.95, 3)["confidence_level"] == "high"


def test_evidence_summary_zero_evidence_is_insufficient():
    summary = evidence_summary(0.0, 0)
    assert summary["mastery_score"] == 0.0
    assert summary["confidence_level"] == "insufficient"


# ---- compute_mastery_evidence：端到端 cap 行为 ----
def test_only_engagement_never_raises_mastery():
    # 纯提问 / 看解析 / 问 hint：不参与掌握度，mastery 恒为 0
    recs = [
        _rec(event_type="ask", user_answer=None, is_correct=None),
        _rec(event_type="concept_inquiry", user_answer=None, is_correct=None),
    ]
    score, count, level = compute_mastery_evidence(recs)
    assert score == 0.0
    assert count == 0
    assert level == "insufficient"


def test_one_correct_capped_at_0_5():
    score, count, level = compute_mastery_evidence([_rec()])
    assert count == 1
    assert level == "low"
    assert score <= 0.5
    # 全对且近期作答时原算法给满分，cap 必把它压到 0.5
    assert score == 0.5


def test_two_correct_capped_at_0_8():
    score, count, level = compute_mastery_evidence([_rec(rid="r1"), _rec(rid="r2")])
    assert count == 2
    assert level == "medium"
    assert score <= 0.8
    assert score == 0.8


def test_five_correct_no_cap_and_high_confidence():
    recs = [_rec(rid=f"r{i}") for i in range(5)]
    score, count, level = compute_mastery_evidence(recs)
    assert count == 5
    assert level == "high"
    # 证据充足时不设上限，满分可达成
    assert score == 1.0


def test_engagement_does_not_inflate_mastery():
    # 1 次真正作答 + 20 次提问，掌握度仍只按 1 条证据封顶
    recs = [_rec(rid="real")]
    for i in range(20):
        recs.append(_rec(event_type="ask", rid=f"chat{i}", user_answer=None, is_correct=None))
    score, count, level = compute_mastery_evidence(recs)
    assert count == 1
    assert level == "low"
    assert score == 0.5


def test_confidence_level_escalates_with_evidence():
    _, c1, l1 = compute_mastery_evidence([_rec(rid="r1")])
    _, c2, l2 = compute_mastery_evidence([_rec(rid="r1"), _rec(rid="r2")])
    _, c5, l5 = compute_mastery_evidence([_rec(rid=f"r{i}") for i in range(5)])
    assert (c1, l1) == (1, "low")
    assert (c2, l2) == (2, "medium")
    assert (c5, l5) == (5, "high")


# ---- 幂等 + user 隔离 ----
def test_duplicate_events_are_idempotent():
    # 同一 attempt_id 的重复流水只算一条证据
    dup = [_rec(rid="r1", metadata_={"attempt_id": "a1"}) for _ in range(3)]
    assert len(unique_evidence(dup)) == 1
    score, count, _ = compute_mastery_evidence(dup)
    assert count == 1
    assert score == 0.5


def test_mixed_users_raise_in_unique_evidence():
    mixed = [
        _rec(user_id="u1", rid="r1", metadata_={"attempt_id": "a1"}),
        _rec(user_id="u2", rid="r2", metadata_={"attempt_id": "a2"}),
    ]
    import pytest
    with pytest.raises(ValueError):
        unique_evidence(mixed)


# ---- 原时间/难度加权算法仍生效（只加 cap，未重写）----
def test_time_decay_weighting_preserved():
    # 同一个"一正一误"集合：当错误答案很旧时，它对掌握度影响应趋近于 0，
    # 证明 _calculate_mastery 的时间衰减权重依然活跃。
    recent = _now() - timedelta(days=1)
    old = _now() - timedelta(days=100)

    set_a = [  # 一正一误都较新 → 权重相当 → 约 0.5
        _rec(rid="ok", is_correct=True, created_at=recent),
        _rec(rid="bad", is_correct=False, created_at=recent),
    ]
    set_b = [  # 正确较新、错误极旧 → 旧错误权重≈0 → 接近满分
        _rec(rid="ok", is_correct=True, created_at=recent),
        _rec(rid="bad", is_correct=False, created_at=old),
    ]
    _, _, _ = compute_mastery_evidence(set_a)
    score_a = compute_mastery_evidence(set_a)[0]
    score_b = compute_mastery_evidence(set_b)[0]
    assert score_b > score_a
