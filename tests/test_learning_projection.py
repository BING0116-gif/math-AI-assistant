from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.learning_projection import CALCULATION_VERSION, _calculate_state


def _attempt(number, *, correct, kind="regular", days=0, difficulty=3, hint=False, solution=False, spent=None):
    return SimpleNamespace(
        id=f"attempt-{number}", correct=correct, user_answer="A",
        submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days),
        grading_snapshot={
            "difficulty": difficulty,
            "estimated_time": 100,
            "error_category": None if correct else "KNOWLEDGE_GAP",
            "learning_signals": {
                "attempt_kind": kind, "hint_used": hint,
                "solution_viewed": solution, "review_interval_days": max(1, days),
                "time_spent_seconds": spent,
            },
        },
    )


def test_projection_is_deterministic_and_single_success_is_not_mastery():
    attempts = [_attempt(1, correct=True)]
    first = _calculate_state(attempts)
    second = _calculate_state(attempts)
    assert first == second
    assert first["mastery"] < 0.5
    assert first["confidence"] <= 0.3
    assert first["calculation_version"] == CALCULATION_VERSION
    assert first["evolution_history"][0]["reason"] == "correct_evidence"


def test_variant_and_spaced_success_outweigh_immediate_retry():
    wrong = _attempt(1, correct=False)
    immediate = _calculate_state([wrong, _attempt(2, correct=True, kind="original_retry")])
    variant = _calculate_state([wrong, _attempt(2, correct=True, kind="variant")])
    spaced = _calculate_state([wrong, _attempt(2, correct=True, kind="spaced_review", days=7)])
    assert immediate["mastery"] < variant["mastery"] < spaced["mastery"]
    assert variant["variant_attempts_count"] == 1
    assert variant["variant_performance"] == 1.0
    assert spaced["memory_strength"] > immediate["memory_strength"]


def test_help_and_solution_view_reduce_positive_weight():
    base = [_attempt(1, correct=False)]
    unaided = _calculate_state(base + [_attempt(2, correct=True)])
    aided = _calculate_state(base + [_attempt(2, correct=True, hint=True, solution=True)])
    assert aided["mastery"] < unaided["mastery"]
    assert aided["error_type_counts"] == {"KNOWLEDGE_GAP": 1}
    rushed = _calculate_state(base + [_attempt(2, correct=True, spent=5)])
    assert rushed["mastery"] < unaided["mastery"]
