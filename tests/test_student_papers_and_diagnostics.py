import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, Question, QuestionKnowledgePoint, User
from app.services.practice_diagnostic_service import answer_diagnostic, start_diagnostic
from app.services.practice_service import PracticeError, start_session, submit_attempt
from app.services.student_paper_service import create_paper, finalize_paper, get_paper, launch_paper, update_paper


@pytest_asyncio.fixture
async def student_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="u1", username="u1", email="u1@example.test", password_hash="x"),
            User(id="u2", username="u2", email="u2@example.test", password_hash="x"),
            Course(id="c1", code="calculus", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="v1", course_id="c1", version="1", name="V1", status="published"),
            Chapter(id="ch1", course_id="c1", version_id="v1", code="ch1", name="极限"),
            KnowledgePoint(id="kp1", course_id="c1", version_id="v1", chapter_id="ch1", code="limit", name="极限"),
        ])
        await db.flush()
        for index in range(2):
            question=Question(id=f"Q{index}",content="求 lim sin x / x",question_type="choice",options=[{"id":"A","text":"1"},{"id":"B","text":"0"}],answer="A",analysis="使用等价无穷小",category="高数",difficulty=2,course_id="c1",version_id="v1",review_status="published",grading_mode="deterministic",practice_eligible=True,exam_eligible=True,auto_grading_eligible=True,answer_spec={"kind":"choice","correct":"A"})
            db.add(question);await db.flush();db.add(QuestionKnowledgePoint(question_id=question.id,knowledge_point_id="kp1"))
        await db.commit()
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_student_paper_owner_revision_and_snapshot_launch(student_db):
    paper=await create_paper("u1",{"title":"极限卷","course_id":"c1","version_id":"v1","source_type":"manual","question_ids":["Q0","Q1"]})
    with pytest.raises(PracticeError,match="不存在"): await get_paper("u2",paper["paper_id"])
    with pytest.raises(PracticeError,match="不存在"): await update_paper("u2",paper["paper_id"],{"expected_revision":paper["revision"],"title":"越权修改"})
    with pytest.raises(PracticeError,match="不存在"): await finalize_paper("u2",paper["paper_id"],paper["revision"])
    with pytest.raises(PracticeError,match="不存在"): await launch_paper("u2",paper["paper_id"],{"mode":"practice","behavior":"adaptive","idempotency_key":"cross-user-launch"})
    with pytest.raises(PracticeError,match="其他位置"): await update_paper("u1",paper["paper_id"],{"expected_revision":99,"title":"冲突"})
    ready=await finalize_paper("u1",paper["paper_id"],paper["revision"])
    practice=await launch_paper("u1",paper["paper_id"],{"mode":"practice","behavior":"adaptive","idempotency_key":"paper-practice-key"})
    test=await launch_paper("u1",paper["paper_id"],{"mode":"test","duration_minutes":30,"idempotency_key":"paper-test-key"})
    assert ready["status"]=="ready" and practice["mode"]=="practice" and test["mode"]=="exam"


@pytest.mark.asyncio
async def test_wrong_practice_attempt_can_run_idempotent_diagnostic(student_db):
    paper=await create_paper("u1",{"title":"诊断卷","course_id":"c1","version_id":"v1","question_ids":["Q0"]})
    paper=await finalize_paper("u1",paper["paper_id"],paper["revision"])
    launched=await launch_paper("u1",paper["paper_id"],{"mode":"practice","behavior":"adaptive","idempotency_key":"diagnostic-session"})
    session=await start_session("u1",launched["session_id"])
    await submit_attempt("u1",session["session_id"],"Q0","B","wrong-attempt")
    with pytest.raises(PracticeError, match="不存在"):
        await start_diagnostic("u2", session["session_id"], "Q0", "cross-user-start")
    with pytest.raises(PracticeError, match="不存在"):
        await answer_diagnostic("u2", session["session_id"], "Q0", "A", "cross-user-answer")
    diagnostic=await start_diagnostic("u1",session["session_id"],"Q0","diagnostic-start")
    repeat=await start_diagnostic("u1",session["session_id"],"Q0","another-key")
    answered=await answer_diagnostic("u1",session["session_id"],"Q0","A","diagnostic-answer")
    assert diagnostic["event_id"]==repeat["event_id"] and answered["correct"] is True
