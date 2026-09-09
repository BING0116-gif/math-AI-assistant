import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import AIInteractionRun, Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, PracticeSession, PracticeSessionQuestion, Question, User
from app.services.tutor_service import complete_ai_run, resolve_tutor_context, start_ai_run, tutor_instruction


@pytest.mark.parametrize("mode,required,forbidden", [
    ("hint_only", "禁止直接给最终答案", "完整解法"),
    ("step_by_step", "分步讲解", "内部路由"),
    ("check_my_work", "先要求补充", "直接代做"),
])
def test_tutor_modes_are_explicit_backend_constraints(mode, required, forbidden):
    instruction = tutor_instruction(mode)
    assert required in instruction
    assert forbidden in instruction
    assert "内部执行策略" in instruction and "不得向学生暴露" in instruction


def test_unknown_tutor_mode_is_not_silently_downgraded():
    with pytest.raises(KeyError):
        tutor_instruction("react")


@pytest.mark.asyncio
async def test_tutor_context_is_owner_scoped_completion_gated_and_audited(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="user-1", username="student", email="tutor@example.test", password_hash="x"),
            User(id="user-2", username="other", email="other@example.test", password_hash="x"),
            Course(id="course-1", code="calculus", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1", name="V1", status="published"),
            Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="极限"),
            KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限", key_formulas=["lim f(x)"]),
        ])
        await db.flush()
        db.add(Question(id="T-1", content="求极限", question_type="numeric_fill", answer="1", category="高数", course_id="course-1", version_id="version-1"))
        session = PracticeSession(id="exam-1", user_id="user-1", mode="exam", course_id="course-1", version_id="version-1", status="in_progress", config_snapshot={}, random_seed=1, idempotency_key="exam-key")
        db.add(session)
        await db.flush()
        db.add(PracticeSessionQuestion(session_id="exam-1", question_id="T-1", position=1, snapshot={"question_id": "T-1", "content": "求极限", "answer": "1", "analysis": "定义法", "knowledge_point_codes": ["limit"]}))
        await db.commit()

    requested = {"source_session_id": "exam-1", "question_id": "T-1"}
    with pytest.raises(PermissionError, match="考试完成前"):
        await resolve_tutor_context("user-1", "chat-1", "hint_only", requested)
    with pytest.raises(PermissionError, match="不属于"):
        await resolve_tutor_context("user-2", "chat-2", "hint_only", requested)
    async with factory() as db:
        session = await db.get(PracticeSession, "exam-1")
        session.status = "completed"
        await db.commit()

    context, chat_id = await resolve_tutor_context("user-1", "chat-1", "check_my_work", requested)
    assert context["verified_source_question"]["correct_answer"] == "1"
    assert context["knowledge_point_evidence"][0]["code"] == "limit"
    run_id = await start_ai_run("user-1", chat_id, "check_my_work", context)
    await complete_ai_run(run_id, status="completed", metadata={"model": "mock-qwen", "tool_names": ["expression_verify"], "latency_ms": 12})
    async with factory() as db:
        run = await db.scalar(select(AIInteractionRun).where(AIInteractionRun.id == run_id))
        assert run.user_id == "user-1" and run.prompt_version == "tutor-mode-v2-gated"
        assert run.token_usage is None and run.estimated_cost is None
        assert run.tool_names == ["expression_verify"]
    await engine.dispose()
