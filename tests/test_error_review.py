import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Course, ErrorItem, ErrorReviewEvent, KnowledgeGraphVersion,
    PracticeAttempt, PracticeSession, PracticeSessionQuestion, Question, User,
)
from app.services.error_review import capture_wrong_attempt, record_review_evidence


@pytest.mark.asyncio
async def test_wrong_attempts_aggregate_per_owner_and_review_requires_all_evidence():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        db.add_all([
            User(id="user-1", username="u1", email="u1@example.test", password_hash="x"),
            User(id="user-2", username="u2", email="u2@example.test", password_hash="x"),
            Course(id="course-1", code="calculus", name="高等数学", subject="math"),
            KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1", name="V1"),
        ])
        await db.flush()
        question = Question(
            id="Q-1", content="1+1=?", question_type="choice", answer="A",
            answer_spec={"kind": "choice", "correct": "A"}, category="高数",
            course_id="course-1", version_id="version-1",
        )
        db.add(question)
        await db.flush()
        for user_id, attempt_id, session_id, row_id in (
            ("user-1", "attempt-1", "session-1", 1),
            ("user-1", "attempt-2", "session-2", 2),
            ("user-2", "attempt-3", "session-3", 3),
        ):
            session = PracticeSession(id=session_id, user_id=user_id, mode="practice", status="in_progress", course_id="course-1", version_id="version-1", config_snapshot={}, random_seed=1, idempotency_key=session_id)
            db.add(session)
            await db.flush()
            row = PracticeSessionQuestion(id=row_id, session_id=session_id, question_id="Q-1", position=1, snapshot={})
            db.add(row)
            await db.flush()
            attempt = PracticeAttempt(id=attempt_id, user_id=user_id, session_id=session_id, session_question_id=row_id, question_id="Q-1", user_answer="B", correct=False, grading_snapshot={"correct_answer": "A"}, idempotency_key=attempt_id)
            db.add(attempt)
            await capture_wrong_attempt(db, attempt=attempt, question_snapshot={"content": "1+1=?", "question_type": "choice", "knowledge_point_codes": ["limit"]}, classification={"reason": "概念错误", "confidence": 1.0})
        await db.commit()

        items = list((await db.execute(select(ErrorItem).order_by(ErrorItem.user_id))).scalars())
        assert len(items) == 2
        assert items[0].user_id == "user-1" and items[0].wrong_attempt_count == 2
        assert items[1].user_id == "user-2" and items[1].wrong_attempt_count == 1
        assert await db.scalar(select(func.count(ErrorReviewEvent.id)).where(ErrorReviewEvent.event_type == "wrong_attempt")) == 3

        item = items[0]
        await record_review_evidence(db, user_id="user-1", item_id=item.item_id, event_type="spaced_correct", event_id="review-out-of-order")
        assert item.review_state == "new"
        await record_review_evidence(db, user_id="user-1", item_id=item.item_id, event_type="original_correct", event_id="review-original")
        assert item.review_state == "understanding" and not item.is_mastered
        await record_review_evidence(db, user_id="user-1", item_id=item.item_id, event_type="variant_correct", event_id="review-variant")
        assert item.review_state == "consolidating" and not item.is_mastered
        await record_review_evidence(db, user_id="user-1", item_id=item.item_id, event_type="spaced_correct", event_id="review-spaced")
        assert item.review_state == "mastered" and item.is_mastered
        with pytest.raises(LookupError):
            await record_review_evidence(db, user_id="user-2", item_id=item.item_id, event_type="original_correct", event_id="cross-owner")
        await db.commit()
    await engine.dispose()
