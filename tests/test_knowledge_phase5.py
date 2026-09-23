import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource, Question, QuestionKnowledgePoint,
)
from app.services.knowledge_catalog import get_published_course_tree, get_published_point, get_published_learning_content, search_published_points
from app.services.knowledge_content import (
    REQUIRED_GOLDEN_RESOURCE_TYPES,
    ResourcePublishingError,
    chapter_completeness_report,
    publish_calculus_phase5,
    publish_chapter,
    seed_calculus_phase5,
    withdraw_chapter,
)
from app.services.calculus_phase5 import POINTS as PHASE5_POINTS
from app.services.phase5_content import GOLDEN as PHASE5_GOLDEN
from app.services.phase5_standard_content import DESCRIPTIONS as PHASE5_STANDARD_DESCRIPTIONS
from app.services.phase5_standard_content import STANDARD as PHASE5_STANDARD


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase5_seed_builds_98_point_draft_without_bypassing_release_gate(session_factory):
    async with session_factory() as session:
        course = await seed_calculus_phase5(session)
        await seed_calculus_phase5(session)
        await session.commit()

        version = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id,
            KnowledgeGraphVersion.version == "3.0",
        ))
        assert version.status == "draft"
        assert course.default_version_id != version.id
        assert await session.scalar(select(func.count()).select_from(KnowledgePoint).where(
            KnowledgePoint.version_id == version.id,
            KnowledgePoint.status == "active",
        )) == 98
        tree = await get_published_course_tree(session, course.id)
        assert len(tree["chapters"]) == 2
        assert tree["version"]["version"] == "2.0"
        assert all(chapter.status == "draft" for chapter in (await session.scalars(
            select(Chapter).where(Chapter.version_id == version.id)
        )).all())


@pytest.mark.asyncio
async def test_phase5_draft_points_are_not_visible_in_public_search(session_factory):
    async with session_factory() as session:
        course = await seed_calculus_phase5(session)
        await session.commit()
        by_name = await search_published_points(session, course.id, "微积分基本定理")
        by_code = await search_published_points(session, course.id, "volume-revolution")
        assert by_name == []
        assert by_code == []


@pytest.mark.asyncio
async def test_chapter_release_is_version_scoped_and_incomplete_content_is_blocked(session_factory):
    async with session_factory() as session:
        course = await seed_calculus_phase5(session)
        version3 = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == "3.0"
        ))
        chapter = await session.scalar(select(Chapter).where(
            Chapter.version_id == version3.id, Chapter.code == "integral-applications"
        ))
        await withdraw_chapter(session, chapter.id)
        tree3 = await get_published_course_tree(session, course.id)
        tree2 = await get_published_course_tree(session, course.id, "2.0")
        assert tree3["version"]["version"] == "2.0"
        assert [row["name"] for row in tree2["chapters"]] == ["函数、极限与连续", "导数与微分"]
        old_point_id = tree2["chapters"][0]["children"][0]["knowledge_points"][0]["id"]
        assert (await get_published_point(session, old_point_id))["version"]["version"] == "2.0"

        point = await session.scalar(select(KnowledgePoint).where(
            KnowledgePoint.chapter_id == chapter.id
        ))
        point.description = "TODO"
        report = await chapter_completeness_report(session, chapter.id)
        assert not report["complete"]
        with pytest.raises(ResourcePublishingError, match="CHAPTER_INCOMPLETE"):
            await publish_chapter(session, chapter.id, "reviewer")


@pytest.mark.asyncio
async def test_phase5_golden_points_carry_full_resources_and_practice(session_factory):
    async with session_factory() as session:
        course = await seed_calculus_phase5(session)
        await session.commit()
        version = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == "3.0"
        ))

        for code in PHASE5_GOLDEN:
            point = await session.scalar(select(KnowledgePoint).where(
                KnowledgePoint.version_id == version.id, KnowledgePoint.code == code
            ))
            assert point is not None and point.importance >= 0.9
            resources = list((await session.scalars(select(KnowledgePointResource).where(
                KnowledgePointResource.knowledge_point_id == point.id,
                KnowledgePointResource.status == "published",
            ))).all())
            types = {resource.resource_type for resource in resources}
            assert REQUIRED_GOLDEN_RESOURCE_TYPES <= types, (code, REQUIRED_GOLDEN_RESOURCE_TYPES - types)
            for resource in resources:
                validation = (resource.metadata_ or {}).get("math_validation") or {}
                assert validation.get("content_hash") == resource.content_hash
                assert validation.get("validator_id") != resource.reviewed_by

            exercise = next(r for r in resources if r.resource_type == "exercise_set")
            question_ids = (exercise.metadata_ or {}).get("question_ids") or []
            assert len(question_ids) == 5
            for qid in question_ids:
                question = await session.get(Question, qid)
                assert question is not None
                assert question.answer_spec == {"version": 1, "kind": "choice", "correct": question.answer}
                assert {option["id"] for option in question.options} == {"A", "B", "C", "D"}
                link = await session.get(QuestionKnowledgePoint, {"question_id": qid, "knowledge_point_id": point.id})
                assert link is not None and link.is_primary


@pytest.mark.asyncio
async def test_phase5_standard_points_carry_authored_resources(session_factory):
    """Every non-golden chapter 3-6 point must ship authored lesson resources."""
    async with session_factory() as session:
        course = await seed_calculus_phase5(session)
        await session.commit()
        version = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == "3.0"
        ))
        all_codes = {code for code, _, _, _, _, _ in PHASE5_POINTS}
        standard_codes = sorted(all_codes - set(PHASE5_GOLDEN))
        assert set(standard_codes) == set(PHASE5_STANDARD)
        assert len(standard_codes) == 39

        core_types = {"intuition", "definition", "formula", "worked_example", "common_error"}
        for code in standard_codes:
            point = await session.scalar(select(KnowledgePoint).where(
                KnowledgePoint.version_id == version.id, KnowledgePoint.code == code
            ))
            assert point is not None and 0 < point.importance < 0.9
            assert point.description == PHASE5_STANDARD_DESCRIPTIONS[code]
            resources = list((await session.scalars(select(KnowledgePointResource).where(
                KnowledgePointResource.knowledge_point_id == point.id,
                KnowledgePointResource.status == "published",
            ))).all())
            types = {resource.resource_type for resource in resources}
            assert core_types <= types, (code, core_types - types)
            assert {"summary", "source_reference"} <= types, code
            for resource in resources:
                assert resource.body.strip()
                validation = (resource.metadata_ or {}).get("math_validation") or {}
                assert validation.get("content_hash") == resource.content_hash
                assert validation.get("validator_id") != resource.reviewed_by


@pytest.mark.asyncio
async def test_publish_calculus_phase5_releases_six_chapters_as_default(session_factory):
    async with session_factory() as session:
        report = await publish_calculus_phase5(session)
        await session.commit()

        assert report["version"] == "3.0" and report["point_count"] == 98
        assert len(report["chapters"]) == 6
        assert all(chapter["complete"] for chapter in report["chapters"])

        course = await session.get(Course, report["course_id"])
        assert course.default_version_id == report["default_version_id"]
        tree = await get_published_course_tree(session, course.id)
        assert tree["version"]["version"] == "3.0"
        assert [row["name"] for row in tree["chapters"]] == [
            "函数、极限与连续", "导数与微分", "中值定理与导数应用", "不定积分", "定积分", "定积分的应用",
        ]
        visible = sum(
            len(section["knowledge_points"])
            for root in tree["chapters"]
            for section in [root, *root["children"]]
        )
        assert visible == 98

        hits = await search_published_points(session, course.id, "微积分基本定理")
        assert [row["name"] for row in hits] == ["微积分基本定理"]

        point = await session.scalar(select(KnowledgePoint).where(
            KnowledgePoint.version_id == report["default_version_id"],
            KnowledgePoint.code == "fundamental-calculus-theorem",
        ))
        content = await get_published_learning_content(session, point.id)
        assert REQUIRED_GOLDEN_RESOURCE_TYPES <= {row["type"] for row in content["resources"]}


@pytest.mark.asyncio
async def test_publish_phase5_is_idempotent_and_reseeding_keeps_release(session_factory):
    async with session_factory() as session:
        first = await publish_calculus_phase5(session)
        await session.commit()

        second = await publish_calculus_phase5(session)
        await session.commit()
        assert second["default_version_id"] == first["default_version_id"]
        version = await session.get(KnowledgeGraphVersion, first["default_version_id"])
        assert version.status == "published"
        questions = await session.scalar(select(func.count()).select_from(Question).where(Question.id.like("P5%")))
        assert questions == 65

        # Re-seeding after release refreshes content but must not demote 3.0.
        course = await seed_calculus_phase5(session)
        await session.commit()
        version = await session.get(KnowledgeGraphVersion, first["default_version_id"])
        assert version.status == "published"
        course = await session.get(Course, course.id)
        assert course.default_version_id == first["default_version_id"]
