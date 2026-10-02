"""Phase 3 student-path contract and compatibility regression tests."""
from types import SimpleNamespace

from fastapi import FastAPI

from app.api import (
    assessment_api,
    chat_api,
    error_api,
    exam_api,
    knowledge_api,
    learning_hub_api,
    practice_api,
    profile_api,
    recommendation_api,
)
from app.api.student_contracts import StudentOperationEnvelope
from app.services.profile_read_models import profile_response, report_response


def _openapi() -> dict:
    app = FastAPI()
    for router in (
        knowledge_api.router,
        practice_api.router,
        assessment_api.router,
        exam_api.router,
        learning_hub_api.router,
        chat_api.router,
        error_api.router,
        profile_api.router,
        recommendation_api.router,
    ):
        app.include_router(router)
    return app.openapi()


def test_main_student_paths_have_success_and_failure_contracts():
    schema = _openapi()
    operations = {
        ("/api/knowledge/courses/{course_id}/learning-map", "get"),
        ("/api/practice/sessions", "post"),
        ("/api/assessments/sessions/{session_id}/submit", "post"),
        ("/api/exams/sessions/{session_id}/report", "get"),
        ("/api/learning/dashboard", "get"),
        ("/api/chat/sessions/{session_id}", "get"),
        ("/api/error-book/{error_id}/review", "post"),
        ("/api/profile/me", "get"),
        ("/api/recommend/session", "post"),
    }
    for path, method in operations:
        responses = schema["paths"][path][method]["responses"]
        assert set(("200", "401", "403", "404", "422", "503")) <= set(responses)
        success_schema = responses["200"]["content"]["application/json"]["schema"]
        assert success_schema


def test_legacy_profile_paths_are_documented_as_deprecated():
    schema = _openapi()
    assert schema["paths"]["/api/profile/{user_id}"]["get"]["deprecated"] is True
    assert schema["paths"]["/api/profile/{user_id}/report"]["get"]["deprecated"] is True
    assert schema["paths"]["/api/profile/me"]["get"].get("deprecated") is not True


def test_old_session_payload_keeps_declared_and_extension_fields():
    payload = {
        "code": 0,
        "data": {
            "session_id": "session-1",
            "status": "created",
            "questions": [{"question_id": "Q-1", "content": "1+1", "legacy_hint": "旧字段"}],
            "legacy_extension": {"still": "available"},
        },
    }
    dumped = StudentOperationEnvelope.model_validate(payload).model_dump()
    assert dumped["data"]["legacy_extension"] == {"still": "available"}
    assert dumped["data"]["questions"][0]["legacy_hint"] == "旧字段"


def test_completed_practice_report_accepts_aggregate_correct_count():
    payload = {
        "code": 0,
        "data": {
            "session_id": "session-1",
            "status": "completed",
            "score": 100.0,
            "total": 5,
            "correct": 5,
            "results": [{"question_id": "Q-1", "correct": True}],
        },
    }

    dumped = StudentOperationEnvelope.model_validate(payload).model_dump()

    assert dumped["data"]["correct"] == 5
    assert dumped["data"]["results"][0]["correct"] is True


def test_profile_read_models_share_one_legacy_compatible_projection():
    snapshot = SimpleNamespace(
        user_id="student-1",
        generated_at="2026-09-23T10:00:00+08:00",
        total_questions=10,
        correct_rate=0.8,
        avg_time_per_question=42.5,
        weak_points=[{"category": "limit", "mastery": 0.3}],
        strong_points=["derivative"],
        recommended_difficulty=3,
        behavior={"pace": "steady"},
        error_patterns=[],
        progress_trends=[],
        preferences={"daily_goal_minutes": 30},
        recommendations=[{"type": "review"}],
        get_learning_level=lambda: "intermediate",
    )
    profile = profile_response(snapshot, include_recommendations=True)
    report = report_response(snapshot)
    assert profile["capability"]["knowledge_mastery"] == {"limit": 0.3, "derivative": 0.9}
    assert profile["recommendations"] == snapshot.recommendations
    assert report["overview"]["total_questions"] == 10
    assert report["recommendations"] == snapshot.recommendations
