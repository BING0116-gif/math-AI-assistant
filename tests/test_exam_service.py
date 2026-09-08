import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint,
    LearningRecord, PracticeAttempt, Question, QuestionKnowledgePoint, User,
)
from app.services.exam_service import _pool_shortages, create_exam, exam_report, get_exam, save_exam_draft, start_exam, submit_exam
from app.services.practice_service import PracticeError


@pytest.mark.asyncio
async def test_exam_exact_quota_snapshot_drafts_report_and_idempotent_submit(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    import app.services.exam_service as service
    async def no_refresh(_user_id):
        return None
    monkeypatch.setattr(service, "_refresh_learning", no_refresh)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            Course(id="course-1", code="calculus", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published"),
            Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="极限"),
            KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限"),
            User(id="user-1", username="student", email="exam@example.test", password_hash="x"),
        ])
        await db.flush()
        for index in range(5):
            question = Question(
                id=f"E-{index}", content=f"考试题 {index}", question_type="choice",
                options=[{"id": "A", "text": "正确"}], answer="A", analysis="原始解析",
                category="高数", difficulty=2, course_id="course-1", version_id="version-1",
                review_status="published", grading_mode="deterministic", practice_eligible=True,
                exam_eligible=True, auto_grading_eligible=True,
                answer_spec={"kind": "choice", "correct": "A"},
            )
            db.add(question)
            await db.flush()
            db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()

    config = {
        "course_id": "course-1", "version_id": "version-1",
        "chapter_ids": ["chapter-1"], "knowledge_point_codes": [],
        "difficulty_min": 1, "difficulty_max": 5,
        "question_type_counts": {"choice": 5}, "duration_minutes": 30,
        "idempotency_key": "exam-create-key", "random_seed": 9,
    }
    created = await create_exam("user-1", config)
    assert len(created["questions"]) == 5
    assert [row["position"] for row in created["questions"]] == [1, 2, 3, 4, 5]
    assert all("answer" not in row and "analysis" not in row and "answer_spec" not in row for row in created["questions"])
    assert (await create_exam("user-1", config))["session_id"] == created["session_id"]
    with pytest.raises(PracticeError, match="不存在"):
        await get_exam("other-user", created["session_id"])

    await start_exam("user-1", created["session_id"])
    for index, row in enumerate(created["questions"]):
        saved = await save_exam_draft("user-1", created["session_id"], row["question_id"], "B" if index == 4 else "A", 0)
        assert saved["version"] == 1
    with pytest.raises(PracticeError, match="其他设备"):
        await save_exam_draft("user-1", created["session_id"], created["questions"][0]["question_id"], "B", 0)

    # Existing sessions remain immutable after the source question is edited.
    async with factory() as db:
        question = await db.get(Question, created["questions"][0]["question_id"])
        question.content = "已编辑题干"
        question.answer = "B"
        question.answer_spec = {"kind": "choice", "correct": "B"}
        await db.commit()

    report = await submit_exam("user-1", created["session_id"])
    assert report["score"] == 80.0 and report["correct"] == 4
    assert report["questions"][0]["content"] != "已编辑题干"
    assert report["questions"][0]["correct_answer"] == "A"
    assert (await submit_exam("user-1", created["session_id"]))["score"] == 80.0
    assert (await exam_report("user-1", created["session_id"]))["completion_reason"] == "submitted"
    async with factory() as db:
        assert await db.scalar(select(func.count(PracticeAttempt.id))) == 5
        assert await db.scalar(select(func.count(LearningRecord.id)).where(LearningRecord.event_type == "exam_answer")) == 5
        assert await db.scalar(select(func.count(ErrorItem.item_id)).where(ErrorItem.user_id == "user-1")) == 1

    timeout_config = {**config, "idempotency_key": "exam-timeout-key", "random_seed": 10}
    timed = await create_exam("user-1", timeout_config)
    await start_exam("user-1", timed["session_id"])
    from app.data.models import PracticeSession
    async with factory() as db:
        timeout_session = await db.get(PracticeSession, timed["session_id"])
        timeout_session.started_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        await db.commit()
    expired = await get_exam("user-1", timed["session_id"])
    assert expired["status"] == "completed" and expired["completion_reason"] == "timeout"
    timeout_report = await exam_report("user-1", timed["session_id"])
    assert timeout_report["error_breakdown"] == [{"category": "UNANSWERED", "count": 5}]
    await engine.dispose()


def test_exam_shortage_reports_each_question_type():
    shortages = _pool_shortages({"choice": 3, "judge": 2}, {"choice": [object(), object()], "judge": []})
    assert shortages == {
        "choice": {"requested": 3, "available": 2},
        "judge": {"requested": 2, "available": 0},
    }
