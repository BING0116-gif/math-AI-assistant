import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, KnowledgeGraphVersion
from app.services.knowledge_catalog import get_published_course_tree, get_published_learning_content, get_published_point
from app.services.knowledge_content import publish_calculus_phase5
from app.services.knowledge_seed import seed_phase_one_calculus


@pytest.mark.asyncio
async def test_phase_one_seed_is_idempotent_and_exposes_sorted_tree():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        course = await seed_phase_one_calculus(session)
        await seed_phase_one_calculus(session)
        await session.commit()
        tree = await get_published_course_tree(session, course.id)
        assert tree["version"]["status"] == "published"
        assert [chapter["name"] for chapter in tree["chapters"]] == ["函数、极限与连续"]
        sections = tree["chapters"][0]["children"]
        assert [section["sort_order"] for section in sections] == [1, 2, 3, 4]
        assert [section["name"] for section in sections] == ["函数基础", "极限概念", "极限计算", "连续性"]
        points = [point for section in sections for point in section["knowledge_points"]]
        assert len(points) == 24
        point_codes = {point["code"] for point in points}
        assert len(point_codes) == 24  # 知识点 code 唯一
        detail = await get_published_point(session, points[0]["id"])
        assert detail["learning_objectives"]
        assert detail["key_concepts"]
        assert detail["exam_focuses"]
        # Step 1.1：前置/关联关系已暴露
        assert "prerequisites" in detail
        assert "related" in detail
        learning = await get_published_learning_content(session, points[0]["id"])
        assert {resource["type"] for resource in learning["resources"]} == {"concept", "formula", "exam_focus", "example", "exercise"}

        # 前置检查必须以中文名展示：learning 内容附带 code→name 映射。
        with_prereq = None
        for p in points:
            detail_p = await get_published_point(session, p["id"])
            if detail_p["prerequisites"]:
                with_prereq = p
                break
        assert with_prereq is not None
        learning_with_prereq = await get_published_learning_content(session, with_prereq["id"])
        mapped = learning_with_prereq["prerequisite_points"]
        assert mapped and all(entry["name"] and entry["name"] != entry["code"] for entry in mapped)
    await engine.dispose()


@pytest.mark.asyncio
async def test_startup_seed_never_demotes_released_default():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        report = await publish_calculus_phase5(session)
        await session.commit()

        # Simulates an app restart: lifespan re-runs the Phase 1 startup seed.
        await seed_phase_one_calculus(session)
        await session.commit()

        course_tree = await get_published_course_tree(session, report["course_id"])
        assert course_tree["version"]["version"] == "3.0"
        assert [chapter["name"] for chapter in course_tree["chapters"]] == [
            "函数、极限与连续", "导数与微分", "中值定理与导数应用", "不定积分", "定积分", "定积分的应用",
        ]

        # A course whose default points at a non-published version is repaired
        # back to the published Phase 1 catalog.
        version_3 = await session.scalar(select(KnowledgeGraphVersion).where(
            KnowledgeGraphVersion.course_id == report["course_id"],
            KnowledgeGraphVersion.version == "3.0",
        ))
        version_3.status = "draft"
        await session.commit()
        await seed_phase_one_calculus(session)
        await session.commit()
        course_tree = await get_published_course_tree(session, report["course_id"])
        assert course_tree["version"]["version"] == "1.0"
    await engine.dispose()
