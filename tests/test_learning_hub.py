import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select


@pytest.fixture(scope="module", autouse=True)
def database():
    folder = tempfile.mkdtemp(prefix="learning_hub_")
    os.environ["ASYNC_DATABASE_URL"] = f"sqlite+aiosqlite:///{folder}/hub.db"
    from app.data.database import close_db, init_db
    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


async def _seed():
    from app.data.database import get_db_session
    from app.data.models import ReviewSchedule, User, UserKnowledgeState
    async with get_db_session() as db:
        db.add_all([
            User(id="hub-user-a", username="hub-a", email="a@hub.test", password_hash="x"),
            User(id="hub-user-b", username="hub-b", email="b@hub.test", password_hash="x"),
        ])
        await db.flush()
        db.add_all([
            UserKnowledgeState(user_id="hub-user-a", knowledge_point_code="CALC", attempts_count=3, correct_count=1, mastery=.31, memory_strength=.22, confidence=.42, mistake_count=2, error_type_counts={"KNOWLEDGE_GAP": 2}),
            ReviewSchedule(user_id="hub-user-a", knowledge_point_code="CALC", due_at=datetime.now(timezone.utc) - timedelta(hours=1), interval_days=1),
        ])


@pytest.mark.asyncio
async def test_due_review_is_owner_scoped_and_defer_is_idempotent():
    from app.data.database import get_db_session
    from app.data.models import ReviewScheduleAction
    from app.services.learning_hub import defer_review, due_reviews
    await _seed()
    mine = await due_reviews("hub-user-a")
    other = await due_reviews("hub-user-b")
    assert len(mine["items"]) == 1
    assert other["items"] == []
    schedule_id = mine["items"][0]["id"]
    first = await defer_review("hub-user-a", schedule_id, hours=24, idempotency_key="defer-hub-0001")
    second = await defer_review("hub-user-a", schedule_id, hours=24, idempotency_key="defer-hub-0001")
    assert first == second
    assert (await due_reviews("hub-user-a"))["items"] == []
    async with get_db_session() as db:
        assert (await db.execute(select(func.count()).select_from(ReviewScheduleAction))).scalar_one() == 1


@pytest.mark.asyncio
async def test_today_tasks_explain_real_evidence_and_cold_start_degrades_explicitly():
    from app.services.learning_hub import today_hub, unified_dashboard
    existing = await today_hub("hub-user-a")
    task = existing["primary"]
    assert task["evidence"]
    assert any(item["type"] in {"mastery", "due_review"} for item in task["evidence"])
    assert task["degradation"]["code"] == "QUESTION_POOL_EMPTY"
    cold = await today_hub("hub-user-b")
    assert cold["cold_start"] is True
    assert cold["primary"]["type"] == "diagnostic"
    assert cold["primary"]["degradation"]["code"] == "QUESTION_POOL_EMPTY"
    dashboard = await unified_dashboard("hub-user-b")
    assert dashboard["status"] == "discovering"
    assert dashboard["dimensions"]["mastery"] == []
    assert "0%" not in dashboard["status_message"]


@pytest.mark.asyncio
async def test_completed_review_requires_owned_attempt_and_advances_schedule():
    from app.data.database import get_db_session
    from app.data.models import (
        Course, KnowledgeGraphVersion, PracticeAttempt, PracticeSession,
        PracticeSessionQuestion, Question, ReviewSchedule,
    )
    from app.services.learning_hub import LearningHubError, complete_review

    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        db.add(Course(id="hub-course", code="hub-course", name="高等数学", subject="math"))
        db.add(KnowledgeGraphVersion(id="hub-version", course_id="hub-course", version="1", name="V1"))
        await db.flush()
        db.add(Question(id="HUB-Q1", content="1+1=?", question_type="numeric_fill", answer="2", category="高数", course_id="hub-course", version_id="hub-version"))
        db.add(PracticeSession(id="hub-session", user_id="hub-user-a", mode="practice", status="completed", course_id="hub-course", version_id="hub-version", config_snapshot={}, random_seed=1, idempotency_key="hub-session-key"))
        await db.flush()
        row = PracticeSessionQuestion(session_id="hub-session", question_id="HUB-Q1", position=1, snapshot={})
        db.add(row)
        await db.flush()
        attempt = PracticeAttempt(id="hub-attempt", user_id="hub-user-a", session_id="hub-session", session_question_id=row.id, question_id="HUB-Q1", user_answer="2", correct=True, grading_snapshot={"knowledge_point_codes":["CALC"]}, idempotency_key="hub-attempt-key", submitted_at=now)
        db.add(attempt)
        schedule = await db.scalar(select(ReviewSchedule).where(ReviewSchedule.user_id == "hub-user-a"))
        schedule.last_attempt_id = attempt.id
        schedule.updated_at = now + timedelta(minutes=1)
        schedule_id = schedule.id

    first = await complete_review("hub-user-a", schedule_id, attempt_id="hub-attempt", idempotency_key="complete-hub-0001")
    second = await complete_review("hub-user-a", schedule_id, attempt_id="hub-attempt", idempotency_key="complete-hub-0001")
    assert first == second
    assert first["review_count"] == 1
    assert first["stage"] == 1
    assert first["interval_days"] == 3
    assert datetime.fromisoformat(first["due_at"]) >= now + timedelta(days=3)
    with pytest.raises(LearningHubError) as denied:
        await complete_review("hub-user-b", schedule_id, attempt_id="hub-attempt", idempotency_key="complete-hub-other")
    assert denied.value.code == "REVIEW_NOT_FOUND"


@pytest.mark.asyncio
async def test_dashboard_profile_recommendation_and_agent_share_canonical_state():
    from agent_core.agent import MathAgent
    from agent_core.memory_persistence import MemoryPersistenceFacade
    from app.services.learning_hub import unified_dashboard
    from app.services.rag_recommender import RAGRecommender

    dashboard = await unified_dashboard("hub-user-a")
    expected = next(item["value"] for item in dashboard["dimensions"]["mastery"] if item["code"] == "CALC")
    facade = MemoryPersistenceFacade()
    snapshot = await facade.refresh_profile_snapshot("hub-user-a")
    skill = next(item for item in snapshot.skills if item["skill_code"] == "CALC")
    recommendation_profile = await RAGRecommender()._get_user_profile("hub-user-a")
    recommendation_skill = next(item for item in recommendation_profile["skills"] if item["skill_code"] == "CALC")
    prompt_text = MathAgent._format_skill_profile_for_llm(snapshot)

    assert skill["mastery_level"] == pytest.approx(expected)
    assert recommendation_skill["mastery_level"] == pytest.approx(expected)
    assert "CALC" in prompt_text


@pytest.mark.asyncio
async def test_activity_is_owner_scoped_idempotent_and_dashboard_uses_sql_facts():
    from app.data.database import get_db_session
    from app.data.models import LearningActivitySession
    from app.services.learning_activity import ActivityError, end_activity, heartbeat_activity, start_activity
    from app.services.learning_hub import unified_dashboard

    first = await start_activity("hub-user-a", "activity-client-0001", "knowledge", "CALC")
    second = await start_activity("hub-user-a", "activity-client-0001", "knowledge", "CALC")
    assert first["id"] == second["id"]
    async with get_db_session() as db:
        row = await db.get(LearningActivitySession, first["id"])
        row.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    beat = await heartbeat_activity("hub-user-a", first["id"])
    assert beat["active_seconds"] >= 30
    ended = await end_activity("hub-user-a", first["id"])
    assert ended["status"] == "ended"
    with pytest.raises(ActivityError):
        await heartbeat_activity("hub-user-b", first["id"])
    dashboard = await unified_dashboard("hub-user-a", period="7d")
    assert dashboard["metrics"]["active_seconds"]["value"] >= 30
    assert dashboard["metrics"]["active_seconds"]["sample_size"] == 1
    assert dashboard["metrics"]["accuracy"]["value"] is not None
    assert dashboard["data_quality"]["sources"] == ["practice_attempts", "learning_activity_sessions", "user_knowledge_states"]


@pytest.mark.asyncio
async def test_personal_forgetting_curve_stays_hidden_without_required_evidence():
    from app.services.learning_hub import unified_profile
    profile = await unified_profile("hub-user-a")
    assert profile["forgetting_curve"]["status"] == "collecting"
    assert profile["forgetting_curve"]["observations"] == []
    assert profile["forgetting_curve"]["required"] == {"distinct_intervals": 3, "span_days": 7}
