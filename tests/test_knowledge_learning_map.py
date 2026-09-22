import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(scope="module", autouse=True)
def database():
    folder = tempfile.mkdtemp(prefix="knowledge_map_")
    os.environ["ASYNC_DATABASE_URL"] = f"sqlite+aiosqlite:///{folder}/map.db"
    from app.data.database import close_db, init_db
    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


async def _seed():
    from app.data.database import get_db_session
    from app.data.models import Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint, ReviewSchedule, User, UserKnowledgeState
    from app.services.learning_projection import policy_version

    async with get_db_session() as db:
        db.add_all([
            User(id="map-user-a", username="map-a", email="map-a@test.local", password_hash="x"),
            User(id="map-user-b", username="map-b", email="map-b@test.local", password_hash="x"),
        ])
        course = Course(id="map-course", code="MAP", name="高等数学", subject="math", status="active")
        db.add(course)
        await db.flush()
        version = KnowledgeGraphVersion(id="map-version", course_id=course.id, version="1", name="V1", status="published")
        db.add(version)
        await db.flush()
        course.default_version_id = version.id
        chapter = Chapter(id="map-chapter", course_id=course.id, version_id=version.id, code="C1", name="第一章", sort_order=1)
        db.add(chapter)
        await db.flush()
        db.add_all([
            KnowledgePoint(id="map-p1", course_id=course.id, version_id=version.id, chapter_id=chapter.id, code="BASE", name="基础", prerequisites=[], sort_order=1, status="active"),
            KnowledgePoint(id="map-p2", course_id=course.id, version_id=version.id, chapter_id=chapter.id, code="NEXT", name="进阶", prerequisites=["BASE"], sort_order=2, status="active"),
            KnowledgePoint(id="map-p3", course_id=course.id, version_id=version.id, chapter_id=chapter.id, code="LATER", name="后续", prerequisites=["NEXT"], sort_order=3, status="active"),
        ])
        db.add(UserKnowledgeState(
            user_id="map-user-a", knowledge_point_code="BASE", attempts_count=3, correct_count=1,
            mastery=.25, confidence=.4, calculation_version=policy_version(),
        ))
        db.add(ReviewSchedule(
            user_id="map-user-a", knowledge_point_code="BASE",
            due_at=datetime.now(timezone.utc) - timedelta(hours=1), interval_days=1,
        ))
        db.add(ErrorItem(
            user_id="map-user-a", item_id="map-error", question="基础错题",
            knowledge_point_codes=["BASE"], is_mastered=False,
            next_review_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        ))


@pytest.mark.asyncio
async def test_learning_map_is_owner_scoped_and_due_review_is_primary():
    from app.data.database import get_db_session
    from app.services.knowledge_learning_map import build_learning_map

    await _seed()
    async with get_db_session() as db:
        mine = await build_learning_map(db, "map-course", "map-user-a")
        other = await build_learning_map(db, "map-course", "map-user-b")

    mine_by_code = {row["code"]: row for row in mine["points"]}
    other_by_code = {row["code"]: row for row in other["points"]}
    assert mine_by_code["BASE"]["status"] == "weak"
    assert mine_by_code["BASE"]["due_error_count"] == 1
    assert mine["primary_recommendation"]["knowledge_point_code"] == "BASE"
    assert mine["primary_recommendation"]["reason_code"] == "DUE_REVIEW"
    assert len(mine["secondary_recommendations"]) <= 2
    assert other_by_code["BASE"]["attempts"] == 0
    assert other_by_code["BASE"]["open_error_count"] == 0
    assert other_by_code["NEXT"]["status"] == "locked"
    assert other_by_code["NEXT"]["missing_prerequisites"] == ["BASE"]


@pytest.mark.asyncio
async def test_no_answer_evidence_never_becomes_mastered():
    from app.data.database import get_db_session
    from app.services.knowledge_learning_map import build_learning_map

    async with get_db_session() as db:
        projection = await build_learning_map(db, "map-course", "map-user-b")
    assert all(row["status"] != "mastered" for row in projection["points"])
