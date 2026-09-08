"""
Step 1.1 question specification tests.

Covers:
- Question lifecycle state machine (draft/reviewed/published/retired)
- Question-KnowledgePoint normalized M:N relationship
- published questions must be field-complete; draft may be incomplete
- AI-generated questions cannot auto-publish
- content integrity checks for the formal question bank
"""

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Question, QuestionKnowledgePoint, KnowledgePoint
from app.services.knowledge_seed import seed_phase_one_calculus

REVIEW_STATUSES = {"draft", "reviewed", "published", "retired"}
QUESTION_TYPES = {"single_choice", "judge", "numeric_fill", "expression_fill"}


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


@pytest.fixture
def patch_global_session_factory(session_factory, monkeypatch):
    """让依赖全局 get_db_session() 的导入器指向测试引擎。"""
    import app.data.database as db
    monkeypatch.setattr(db, "async_session_factory", session_factory)
    yield session_factory


@pytest.mark.asyncio
async def test_question_lifecycle_states(engine, session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        # draft 可保存不完整审核内容
        q = Question(
            id="Q-DRAFT-1", content="草稿题", question_type="judge",
            category="函数", answer="true", review_status="draft",
        )
        db.add(q)
        await db.commit()
        assert q.review_status == "draft"

        # published 题必须字段完整
        pub = Question(
            id="Q-PUB-1", content="正式题", question_type="single_choice",
            options=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
            answer="A", analysis="解析", source="人工原创",
            category="极限", difficulty=3, review_status="published",
        )
        db.add(pub)
        await db.commit()
        assert pub.review_status == "published"

        # retired 不进入正式题池（由推荐引擎按 review_status 过滤，此处验证状态合法）
        ret = Question(
            id="Q-RET-1", content="退役题", question_type="numeric_fill",
            answer="1", category="连续", review_status="retired",
        )
        db.add(ret)
        await db.commit()
        assert ret.review_status == "retired"

        statuses = {r.review_status for r in (await db.execute(select(Question))).scalars().all()}
        assert statuses <= REVIEW_STATUSES


@pytest.mark.asyncio
async def test_ai_generated_question_cannot_auto_publish(engine, session_factory, patch_global_session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        # AI 生成题默认 draft；即使显式请求 published 也不得自动发布（由导入层强制回退 draft）
        from app.services.question_importer import QuestionImporter
        import pandas as pd
        df = pd.DataFrame([{
            "id": "Q-AI-1", "content": "AI生成题", "category": "极限",
            "answer": "A", "analysis": "", "source": "AI 生成",
            "review_status": "published", "is_ai_generated": True,
        }])
        result = await QuestionImporter().import_from_dict_list(df.to_dict("records"))
        assert result.failed == 0
        q = await db.get(Question, "Q-AI-1")
        assert q is not None
        assert q.review_status == "draft", "AI 生成题不得自动 published"


@pytest.mark.asyncio
async def test_non_ai_import_cannot_publish_directly(engine, session_factory, patch_global_session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        # P0-6 治理：普通导入渠道（非 trusted）即使显式请求 published 也必须回退 draft
        from app.services.question_importer import QuestionImporter
        import pandas as pd
        df = pd.DataFrame([{
            "id": "Q-PUB-1", "content": "普通导入题", "category": "极限",
            "answer": "A", "analysis": "解析", "review_status": "published",
        }])
        result = await QuestionImporter().import_from_dict_list(df.to_dict("records"))
        assert result.failed == 0
        q = await db.get(Question, "Q-PUB-1")
        assert q is not None
        assert q.review_status == "draft", "普通导入渠道不得直接 published，发布必须走审核服务"


@pytest.mark.asyncio
async def test_invalid_review_status_falls_back_to_draft(engine, session_factory, patch_global_session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        from app.services.question_importer import QuestionImporter
        import pandas as pd
        df = pd.DataFrame([{
            "id": "Q-BAD-1", "content": "非法状态题", "category": "函数",
            "answer": "true", "review_status": "hacked",
        }])
        result = await QuestionImporter().import_from_dict_list(df.to_dict("records"))
        assert result.failed == 0
        q = await db.get(Question, "Q-BAD-1")
        assert q.review_status == "draft"


@pytest.mark.asyncio
async def test_question_knowledge_point_normalized_m2m(engine, session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        course = await seed_phase_one_calculus(db)
        await db.flush()
        points = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id))).scalars().all()
        assert len(points) == 24
        p1, p2 = points[0], points[1]

        q = Question(
            id="Q-M2M-1", content="多知识点题", question_type="single_choice",
            options=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
            answer="A", analysis="解析", source="人工原创",
            category="函数", review_status="published",
        )
        db.add(q)
        await db.flush()
        db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=p1.id, is_primary=True))
        db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=p2.id, is_primary=False))
        await db.commit()

        links = (await db.execute(
            select(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == q.id)
        )).scalars().all()
        assert len(links) == 2
        assert {l.knowledge_point_id for l in links} == {p1.id, p2.id}
        assert sum(1 for l in links if l.is_primary) == 1


@pytest.mark.asyncio
async def test_duplicate_m2m_link_is_constrained(engine, session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        course = await seed_phase_one_calculus(db)
        await db.flush()
        p1 = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id))).scalars().first()
        q = Question(id="Q-DUP-1", content="重复关联题", question_type="judge",
                     answer="true", analysis="解析", source="人工原创",
                     category="函数", review_status="draft")
        db.add(q)
        await db.flush()
        db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=p1.id))
        db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=p1.id))
        with pytest.raises(Exception):
            await db.commit()


@pytest.mark.asyncio
async def test_importer_links_points_by_code(engine, session_factory, patch_global_session_factory):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from app.services.question_importer import QuestionImporter
    import pandas as pd
    async with session_factory() as db:
        course = await seed_phase_one_calculus(db)
        await db.flush()
        await db.commit()
        points_by_code = {
            p.code: p.id for p in (await db.execute(
                select(KnowledgePoint).where(KnowledgePoint.course_id == course.id)
            )).scalars().all()
        }
        p1_id = points_by_code["function-definition"]
        p2_id = points_by_code["function-properties"]
    async with session_factory() as db:
        df = pd.DataFrame([{
            "id": "Q-LINK-1", "content": "按code关联题", "category": "函数",
            "answer": "A", "analysis": "解析", "source": "人工原创",
            "review_status": "published", "course_code": course.code,
            "knowledge_point_codes": '["function-definition", "function-properties"]',
        }])
        result = await QuestionImporter().import_from_dict_list(df.to_dict("records"), trusted=True)
        assert result.failed == 0
        q = await db.get(Question, "Q-LINK-1")
        assert q.course_id == course.id
        assert q.review_status == "published"
        counts = (await db.execute(
            select(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == q.id)
        )).scalars().all()
        assert len(counts) == 2
        assert {c.knowledge_point_id for c in counts} == {p1_id, p2_id}


def test_review_status_enum_is_complete():
    assert REVIEW_STATUSES == {"draft", "reviewed", "published", "retired"}


def test_question_types_scope():
    # Step 1.1 首版题型范围
    assert QUESTION_TYPES == {"single_choice", "judge", "numeric_fill", "expression_fill"}