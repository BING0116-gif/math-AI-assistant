"""Pure profile read-model projections used by the profile HTTP API.

Keeping these transformations outside the route module makes the legacy and
``/me`` endpoints share one independently testable contract implementation.
"""
from __future__ import annotations

from typing import Any

from app.services.profile_application import ProfileSnapshot


def profile_response(
    snapshot: ProfileSnapshot,
    *,
    include_recommendations: bool = False,
) -> dict[str, Any]:
    capabilities = {
        point["category"]: point["mastery"] for point in snapshot.weak_points
    }
    for strong_point in snapshot.strong_points:
        capabilities[strong_point] = 0.9

    response: dict[str, Any] = {
        "user_id": snapshot.user_id,
        "generated_at": snapshot.generated_at,
        "summary": {
            "total_questions": snapshot.total_questions,
            "correct_rate": snapshot.correct_rate,
            "avg_time_per_question": snapshot.avg_time_per_question,
            "learning_level": snapshot.get_learning_level(),
        },
        "capability": {
            "knowledge_mastery": capabilities,
            "recommended_difficulty": snapshot.recommended_difficulty,
        },
        "behavior": snapshot.behavior,
        "error_patterns": snapshot.error_patterns,
        "progress_trends": snapshot.progress_trends,
        "preferences": snapshot.preferences,
    }
    if include_recommendations:
        response["recommendations"] = snapshot.recommendations
    return response


def report_response(snapshot: ProfileSnapshot) -> dict[str, Any]:
    return {
        "user_id": snapshot.user_id,
        "generated_at": snapshot.generated_at,
        "overview": {
            "total_questions": snapshot.total_questions,
            "correct_rate": snapshot.correct_rate,
            "avg_time_per_question": snapshot.avg_time_per_question,
            "recommended_difficulty": snapshot.recommended_difficulty,
        },
        "weak_points": snapshot.weak_points,
        "strong_points": snapshot.strong_points,
        "error_patterns": snapshot.error_patterns,
        "progress_trends": snapshot.progress_trends,
        "recommendations": snapshot.recommendations,
    }
