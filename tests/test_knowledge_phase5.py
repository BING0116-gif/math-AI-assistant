import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Chapter, KnowledgeGraphVersion, KnowledgePoint
from app.services.knowledge_catalog import get_published_course_tree, get_published_point, search_published_points
from app.services.knowledge_content import (
    ResourcePublishingError,
    chapter_completeness_report,
    publish_chapter,
    seed_calculus_phase5,
    withdraw_chapter,
)


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
