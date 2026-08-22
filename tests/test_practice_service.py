import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Course, Chapter, ErrorItem, KnowledgeGraphVersion, KnowledgePoint, Question, QuestionKnowledgePoint, User, UserKnowledgeState
from app.services.practice_service import PracticeError, complete_session, create_session, get_session, start_session, submit_attempt


@pytest.mark.asyncio
async def test_practice_session_is_owner_bound_idempotent_and_hides_answers(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        course = Course(id="course-1", code="calculus", name="高等数学", subject="math")
        version = KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published")
        chapter = Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="函数")
        point = KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限")
        user = User(id="user-1", username="student", email="student@example.test", password_hash="x")
        db.add_all([course, version, chapter, point, user])
        await db.flush()
        for index in range(5):
            question = Question(id=f"Q-{index}", content="1+1=?", question_type="choice", options=[{"id": "A", "text": "2"}], answer="A", analysis="因为 1+1=2", category="高数", difficulty=2, course_id="course-1", version_id="version-1", review_status="published", grading_mode="deterministic", practice_eligible=True, answer_spec={"kind": "choice", "correct": "A"})
            db.add(question); await db.flush(); db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()
    config = {"course_id": "course-1", "version_id": "version-1", "chapter_ids": ["chapter-1"], "knowledge_point_codes": [], "question_types": ["choice"], "question_count": 5, "idempotency_key": "create-key-1"}
    session = await create_session("user-1", config)
    assert session["questions"] and "answer_spec" not in session["questions"][0] and "analysis" not in session["questions"][0]
    assert (await create_session("user-1", config))["session_id"] == session["session_id"]
    with pytest.raises(PracticeError, match="不存在"):
        await get_session("other-user", session["session_id"])
    await start_session("user-1", session["session_id"])
    answer = await submit_attempt("user-1", session["session_id"], session["questions"][0]["question_id"], "A", "attempt-1")
    assert answer["correct"] is True and answer["correct_answer"] == "A"
    assert (await submit_attempt("user-1", session["session_id"], session["questions"][0]["question_id"], "A", "attempt-1"))["correct"] is True
    wrong = await submit_attempt("user-1", session["session_id"], session["questions"][1]["question_id"], "B", "attempt-2")
    assert wrong["error_category"] == "UNKNOWN"
    assert wrong["error_classification"]["source"] == "deterministic_rule"
    assert wrong["error_classification"]["version"] == "error-taxonomy-v1"
    async with factory() as db:
        automatic_error = await db.scalar(select(ErrorItem).where(ErrorItem.user_id == "user-1"))
        assert automatic_error is not None
        assert automatic_error.question_id == session["questions"][1]["question_id"]
        assert automatic_error.source == "attempt" and automatic_error.review_state == "new"
    complete = await complete_session("user-1", session["session_id"])
    assert complete["status"] == "completed" and complete["correct"] == 1
    assert complete["error_breakdown"] == [{"category": "UNKNOWN", "count": 4}]
    async with factory() as db:
        state = await db.scalar(select(UserKnowledgeState).where(
            UserKnowledgeState.user_id == "user-1",
            UserKnowledgeState.knowledge_point_code == "limit",
        ))
        snapshot = (state.mastery, state.memory_strength, state.confidence, state.attempts_count, state.calculation_version, state.evolution_history)
    from app.services.learning_projection import rebuild_learning_projections
    await rebuild_learning_projections("user-1")
    async with factory() as db:
        rebuilt = await db.scalar(select(UserKnowledgeState).where(
            UserKnowledgeState.user_id == "user-1",
            UserKnowledgeState.knowledge_point_code == "limit",
        ))
        assert snapshot == (rebuilt.mastery, rebuilt.memory_strength, rebuilt.confidence, rebuilt.attempts_count, rebuilt.calculation_version, rebuilt.evolution_history)
    from app.services.skill_aggregator import SkillAggregator
    aggregator = SkillAggregator()
    assert await aggregator.recalculate_skills("user-1") == 1
    projected_skills = await aggregator.get_all_skills("user-1")
    assert projected_skills[0]["skill_code"] == "limit"
    assert projected_skills[0]["mastery_level"] == rebuilt.mastery
    await engine.dispose()
