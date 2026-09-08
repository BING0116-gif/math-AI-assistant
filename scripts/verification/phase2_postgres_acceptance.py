"""Phase 2 acceptance against an isolated PostgreSQL database.

The caller supplies DATABASE_URL/ASYNC_DATABASE_URL for a disposable database
already migrated to head. No shared student data is read or changed.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func, select

from agent_core.agent import MathAgent
from agent_core.memory_persistence import MemoryPersistenceFacade
from app.data.database import close_db, get_db_session, init_db
from app.data.models import (
    Chapter, Course, ErrorItem, ErrorReviewEvent, KnowledgeGraphVersion, KnowledgePoint,
    PracticeSession, PracticeSessionQuestion, Question, QuestionKnowledgePoint,
    ReviewSchedule, ReviewScheduleAction, User, UserKnowledgeState,
)
from app.services.error_review import record_review_evidence
from app.services.learning_hub import complete_review, today_hub, unified_dashboard
from app.services.practice_service import start_session, submit_attempt
from app.services.rag_recommender import RAGRecommender


USER_A = "phase2-user-a"
USER_B = "phase2-user-b"
QUESTION_ID = "P2-Q1"
CODE = "P2-LIMIT"


async def seed() -> None:
    async with get_db_session() as db:
        db.add_all([
            User(id=USER_A, username="phase2a", email="phase2a@example.test", password_hash="x"),
            User(id=USER_B, username="phase2b", email="phase2b@example.test", password_hash="x"),
            Course(id="p2-course", code="p2-course", name="高等数学验收", subject="math", default_version_id="p2-version"),
            KnowledgeGraphVersion(id="p2-version", course_id="p2-course", version="1", name="V1", status="published"),
        ])
        await db.flush()
        db.add(Chapter(id="p2-chapter", course_id="p2-course", version_id="p2-version", code="P2-CHAPTER", name="验收章节"))
        await db.flush()
        point = KnowledgePoint(id="p2-point", course_id="p2-course", version_id="p2-version", chapter_id="p2-chapter", code=CODE, name="极限验收")
        question = Question(
            id=QUESTION_ID, content="1+1=?", question_type="numeric_fill", answer="2",
            answer_spec={"version": 1, "kind": "numeric_fill", "value": 2}, analysis="1+1=2",
            category="高数", difficulty=2, course_id="p2-course", version_id="p2-version",
            review_status="published", grading_mode="deterministic",
            practice_eligible=True, exam_eligible=True, auto_grading_eligible=True,
        )
        db.add_all([point, question])
        await db.flush()
        db.add(QuestionKnowledgePoint(question_id=QUESTION_ID, knowledge_point_id="p2-point"))


async def make_session(user_id: str, suffix: str, *, review_kind: str | None = None) -> str:
    session_id = f"p2-session-{suffix}"
    snapshot = {
        "content": "1+1=?", "question_type": "numeric_fill",
        "answer_spec": {"version": 1, "kind": "numeric_fill", "value": 2},
        "analysis": "1+1=2", "difficulty": 2,
        "knowledge_point_codes": [CODE],
    }
    config = {"knowledge_point_codes": [CODE]}
    if review_kind:
        config["review_kind"] = review_kind
        config["review_interval_days"] = 1
    async with get_db_session() as db:
        db.add(PracticeSession(
            id=session_id, user_id=user_id, mode="practice", status="created",
            course_id="p2-course", version_id="p2-version", config_snapshot=config,
            random_seed=1, idempotency_key=f"p2-session-key-{suffix}",
        ))
        await db.flush()
        db.add(PracticeSessionQuestion(session_id=session_id, question_id=QUESTION_ID, position=1, snapshot=snapshot))
    await start_session(user_id, session_id)
    return session_id


async def wrong_attempt(user_id: str, suffix: str) -> dict:
    session_id = await make_session(user_id, suffix)
    first = await submit_attempt(user_id, session_id, QUESTION_ID, "3", f"p2-attempt-key-{suffix}")
    second = await submit_attempt(user_id, session_id, QUESTION_ID, "3", f"p2-attempt-key-{suffix}")
    assert first == second
    return first


async def main() -> None:
    await init_db()
    try:
        await seed()
        await wrong_attempt(USER_A, "wrong-a")
        await wrong_attempt(USER_B, "wrong-b")

        async with get_db_session() as db:
            items = list((await db.execute(select(ErrorItem).order_by(ErrorItem.user_id))).scalars())
            assert len(items) == 2 and {item.user_id for item in items} == {USER_A, USER_B}
            item_a = next(item for item in items if item.user_id == USER_A)
            assert item_a.wrong_attempt_count == 1 and item_a.review_state == "new"
            state_before = await db.scalar(select(UserKnowledgeState).where(UserKnowledgeState.user_id == USER_A, UserKnowledgeState.knowledge_point_code == CODE))
            schedule = await db.scalar(select(ReviewSchedule).where(ReviewSchedule.user_id == USER_A, ReviewSchedule.knowledge_point_code == CODE))
            assert state_before and state_before.mistake_count == 1
            assert schedule and schedule.due_at > datetime.now(timezone.utc)
            initial_due = schedule.due_at
            schedule.updated_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            schedule_id = schedule.id

        review_session = await make_session(USER_A, "review-a", review_kind="original_correct")
        review_result = await submit_attempt(USER_A, review_session, QUESTION_ID, "2", "p2-review-attempt-key")
        assert review_result["correct"] is True
        async with get_db_session() as db:
            from app.data.models import PracticeAttempt
            attempt = await db.scalar(select(PracticeAttempt).where(PracticeAttempt.session_id == review_session))
            reviewed = await record_review_evidence(
                db, user_id=USER_A, item_id=item_a.item_id,
                event_type="original_correct", event_id="p2-original-review", attempt_id=attempt.id,
            )
            assert reviewed.review_state == "understanding"
            attempt_id = attempt.id

        completed = await complete_review(
            USER_A, schedule_id, attempt_id=attempt_id,
            idempotency_key="p2-complete-review",
        )
        repeated = await complete_review(
            USER_A, schedule_id, attempt_id=attempt_id,
            idempotency_key="p2-complete-review",
        )
        assert completed == repeated
        assert datetime.fromisoformat(completed["due_at"]) > initial_due

        dashboard = await unified_dashboard(USER_A)
        task = (await today_hub(USER_A))["primary"]
        snapshot = await MemoryPersistenceFacade().refresh_profile_snapshot(USER_A)
        recommendation = await RAGRecommender()._get_user_profile(USER_A)
        expected = next(row["value"] for row in dashboard["dimensions"]["mastery"] if row["code"] == CODE)
        profile_skill = next(row for row in snapshot.skills if row["skill_code"] == CODE)
        recommendation_skill = next(row for row in recommendation["skills"] if row["skill_code"] == CODE)
        assert profile_skill["mastery_level"] == expected
        assert recommendation_skill["mastery_level"] == expected
        assert CODE in MathAgent._format_skill_profile_for_llm(snapshot)
        assert task and task["evidence"]

        async with get_db_session() as db:
            counts = {
                "attempts": await db.scalar(select(func.count()).select_from(__import__("app.data.models", fromlist=["PracticeAttempt"]).PracticeAttempt)),
                "error_items": await db.scalar(select(func.count()).select_from(ErrorItem)),
                "error_events": await db.scalar(select(func.count()).select_from(ErrorReviewEvent)),
                "knowledge_states": await db.scalar(select(func.count()).select_from(UserKnowledgeState)),
                "review_schedules": await db.scalar(select(func.count()).select_from(ReviewSchedule)),
                "review_actions": await db.scalar(select(func.count()).select_from(ReviewScheduleAction)),
            }
        print(json.dumps({
            "status": "passed", "wrong_attempt": "error+state+schedule",
            "review_transition": "new->understanding", "next_due_advanced": True,
            "same_state_mastery": expected, "recommendation_evidence": len(task["evidence"]),
            "owner_isolation": True, **counts,
        }, ensure_ascii=False))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
