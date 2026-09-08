"""
Step 1.1 knowledge point specification tests.

Covers:
- stable code uniqueness
- prerequisites / related codes reference existing points (no dangling references)
- no illegal self-reference in prerequisites / related
- course association correct
- difficulty / importance ranges valid
"""

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Chapter, KnowledgePoint
from app.services.knowledge_seed import POINTS, seed_phase_one_calculus


@pytest.fixture
def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(eng.sync_engine, "connect")
    def _fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    return eng


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def test_seed_point_codes_unique():
    codes = [p[0] for p in POINTS]
    assert len(codes) == len(set(codes)), "知识点 code 必须唯一"


def test_seed_point_count_within_scope():
    # 首版 20~30 个知识点
    assert 20 <= len(POINTS) <= 30


def test_seed_sections_cover_scope():
    sections = [s[0] for s in __import__(
        "app.services.knowledge_seed", fromlist=["SECTIONS"]
    ).SECTIONS]
    assert {"function-basics", "limit-concept", "limit-calculation", "continuity"} <= set(sections)


def test_seed_prerequisites_related_no_self_and_reference_valid():
    codes = {p[0] for p in POINTS}
    for code, _name, _desc, _sec, _sort, _diff, _obj, prereqs, relateds in POINTS:
        for ref in list(prereqs) + list(relateds):
            assert ref != code, f"知识点 {code} 不能自引用自身"
            assert ref in codes, f"知识点 {code} 引用了不存在的知识点 code: {ref}"


@pytest.mark.asyncio
async def test_seeded_points_bind_to_course_and_chapter(engine, session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        course = await seed_phase_one_calculus(db)
        await db.flush()
        points = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id))).scalars().all()
        assert len(points) == 24
        for point in points:
            assert point.code
            assert point.name
            assert point.difficulty in {1, 2, 3, 4, 5}
            assert 0.0 <= point.importance <= 1.0
            chapter = await db.get(Chapter, point.chapter_id)
            assert chapter is not None and chapter.course_id == course.id
        # 每章至少包含一个知识点
        chapter_ids = {p.chapter_id for p in points}
        assert len(chapter_ids) == 4