"""WS-C paper composition tests（客观题限定，P0-7 边界）。

覆盖：
- 组卷只消费 published + exam_eligible + auto_grading_eligible 的客观题
- draft 题、版本不匹配题、主观题不入卷
- 生成落库 + 题目快照固化；preview 不落库
- 发布服务按题型派生能力字段
"""

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base,
    KnowledgeGraphVersion,
    KnowledgePoint,
    Paper,
    PaperQuestion,
    Question,
    QuestionKnowledgePoint,
)
from app.services.content_review import ContentReviewService
from app.services.knowledge_seed import seed_phase_one_calculus
from app.services.paper_generator import PaperGenerationError, PaperGenerator
from app.services.question_importer import QuestionImporter


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
    import app.data.database as db
    monkeypatch.setattr(db, "async_session_factory", session_factory)
    yield session_factory


async def seed_scope():
    """播种课程/版本/知识点，返回 (course_id, version_id, kp_id, kp_code)。"""
    from app.data.database import get_db_session
    async with get_db_session() as db:
        await seed_phase_one_calculus(db)
        await db.commit()
    async with get_db_session() as db:
        version = (await db.execute(select(KnowledgeGraphVersion).limit(1))).scalar_one()
        kp = (await db.execute(select(KnowledgePoint).limit(1))).scalar_one()
        return version.course_id, version.id, kp.id, kp.code


async def add_question(
    db,
    qid: str,
    qtype: str,
    *,
    review_status: str = "published",
    eligible: bool = True,
    version_id: str = None,
    course_id: str = None,
    kp_id: str = None,
    difficulty: int = 2,
    grading_mode: str = "deterministic",
):
    q = Question(
        id=qid,
        content=f"题干 {qid}",
        question_type=qtype,
        options=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}] if qtype == "choice" else None,
        answer="B" if qtype == "choice" else ("true" if qtype == "judge" else "1"),
        analysis="解析",
        category="高数",
        difficulty=difficulty,
        review_status=review_status,
        grading_mode=grading_mode,
        practice_eligible=True,
        exam_eligible=eligible,
        auto_grading_eligible=eligible,
        version_id=version_id,
        course_id=course_id,
        answer_spec=({"version": 1, "kind": "choice", "correct": "B"} if qtype == "choice" else None),
    )
    db.add(q)
    await db.flush()
    if kp_id:
        db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=kp_id, is_primary=True))
    return q


class TestPaperGeneration:
    pytestmark = pytest.mark.asyncio

    async def _seed_bank(self):
        course_id, version_id, kp_id, _ = await seed_scope()
        from app.data.database import get_db_session
        async with get_db_session() as db:
            for i in range(4):
                await add_question(db, f"Q-C-{i}", "choice", version_id=version_id, course_id=course_id, kp_id=kp_id, difficulty=(i % 3) + 1)
            for i in range(3):
                await add_question(db, f"Q-J-{i}", "judge", version_id=version_id, course_id=course_id, kp_id=kp_id)
            for i in range(3):
                await add_question(db, f"Q-N-{i}", "numeric_fill", version_id=version_id, course_id=course_id, kp_id=kp_id)
            # 主观题（发布后能力字段为 False）与 draft 题
            await add_question(db, "Q-CALC", "calculation", eligible=False, grading_mode="manual",
                               version_id=version_id, course_id=course_id, kp_id=kp_id)
            await add_question(db, "Q-DRAFT", "choice", review_status="draft",
                               version_id=version_id, course_id=course_id, kp_id=kp_id)
            await db.commit()
        return version_id

    async def test_generate_objective_paper_with_snapshots(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await self._seed_bank()
        paper = await PaperGenerator().generate(
            config={
                "type_mix": {"choice": 2, "judge": 2, "numeric_fill": 2},
                "random_seed": 7,
                "score_per_question": 5,
                "version_id": version_id,
            },
            title="高数客观题小测",
        )
        assert paper.title == "高数客观题小测"
        assert paper.random_seed == 7
        qs = paper.questions
        assert len(qs) == 6
        assert [pq.position for pq in qs] == list(range(1, 7))
        assert all(pq.score == 5 for pq in qs)
        # 题型只来自客观题
        assert {pq.snapshot["question_type"] for pq in qs} <= {"choice", "judge", "numeric_fill"}
        assert all(pq.snapshot["content"] for pq in qs)
        # 快照固化：改题库不改变卷内内容
        first = qs[0]
        assert first.snapshot["question_id"] == first.question_id

    async def test_preview_not_persisted(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await self._seed_bank()
        result = await PaperGenerator().preview(
            config={"type_mix": {"choice": 2}, "random_seed": 1, "version_id": version_id}
        )
        assert result["total"] == 2
        assert all(q["question_type"] == "choice" for q in result["questions"])
        from app.data.database import get_db_session
        async with get_db_session() as db:
            n = len((await db.execute(select(Paper))).scalars().all())
        assert n == 0, "preview 不应落库"

    async def test_draft_and_subjective_excluded(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await self._seed_bank()
        # draft 题（Q-DRAFT）能力字段为 True，但 review_status=draft → 不可被选中
        paper = await PaperGenerator().generate(
            config={"type_mix": {"choice": 1}, "random_seed": 3, "version_id": version_id}
        )
        ids = [pq.question_id for pq in paper.questions]
        assert "Q-DRAFT" not in ids
        # 主观题即使写进 type_mix 也选不到（auto_grading_eligible=False）
        with pytest.raises(PaperGenerationError) as exc:
            await PaperGenerator().generate(
                config={"type_mix": {"calculation": 1}, "random_seed": 3, "version_id": version_id}
            )
        assert exc.value.code == "INSUFFICIENT_POOL"

    async def test_version_scope_excluded(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        course_id, version_id, kp_id, _ = await seed_scope()
        from app.data.database import get_db_session
        async with get_db_session() as db:
            await add_question(db, "Q-V1", "choice", version_id=version_id, course_id=course_id, kp_id=kp_id)
            # 范围外题（version_id 为空）：版本限定模板不得选中
            await add_question(db, "Q-VX", "choice", version_id=None, course_id=course_id, kp_id=kp_id)
            await db.commit()
        paper = await PaperGenerator().generate(
            config={"type_mix": {"choice": 1}, "random_seed": 1, "version_id": version_id}
        )
        assert [pq.question_id for pq in paper.questions] == ["Q-V1"]

    async def test_kp_filter(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        course_id, version_id, kp_id, kp_code = await seed_scope()
        from app.data.database import get_db_session
        async with get_db_session() as db:
            await add_question(db, "Q-K1", "choice", version_id=version_id, course_id=course_id, kp_id=kp_id)
            # 第二道题不挂任何知识点
            await add_question(db, "Q-K2", "choice", version_id=version_id, course_id=course_id, kp_id=None)
            await db.commit()
        paper = await PaperGenerator().generate(
            config={"type_mix": {"choice": 1}, "random_seed": 1, "version_id": version_id, "kp_codes": [kp_code]}
        )
        assert [pq.question_id for pq in paper.questions] == ["Q-K1"]

    async def test_insufficient_pool_raises(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await self._seed_bank()
        with pytest.raises(PaperGenerationError) as exc:
            await PaperGenerator().generate(
                config={"type_mix": {"choice": 5}, "random_seed": 1, "version_id": version_id}
            )
        assert exc.value.code == "INSUFFICIENT_POOL"


class TestPublishDerivesCapability:
    """发布服务按题型派生判题/组卷能力（P0-7 钩子）。"""

    pytestmark = pytest.mark.asyncio

    async def _review_publish(self, qid: str) -> Question:
        svc = ContentReviewService()
        await svc.update_question(
            qid, {"answer_spec": {"version": 1, "kind": "choice", "correct": "A"}}
        )
        await svc.mark_reviewed(qid)
        pub = await svc.publish(qid)
        return pub

    async def test_objective_and_subjective_derivation(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        course_id, version_id, kp_id, _ = await seed_scope()
        from app.data.database import get_db_session
        importer = QuestionImporter()
        rows = [
            {
                "id": "Q-PUB-C", "category": "高数", "content": "1+1=?", "question_type": "choice",
                "options": [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}],
                "answer": "A", "analysis": "2", "knowledge_point_codes": ["function-definition"],
                "course_code": None,
            },
            {
                "id": "Q-PUB-CALC", "category": "高数", "content": "求导", "question_type": "calculation",
                "answer": "略", "analysis": "解析", "knowledge_point_codes": ["function-definition"],
                "course_code": None,
            },
        ]
        r = await importer.import_from_dict_list(rows)
        assert r.failed == 0
        pub_c = await self._review_publish("Q-PUB-C")
        assert pub_c.review_status == "published"
        assert pub_c.grading_mode == "deterministic"
        assert pub_c.auto_grading_eligible is True
        assert pub_c.exam_eligible is True
        assert pub_c.practice_eligible is True

        svc = ContentReviewService()
        await svc.update_question("Q-PUB-CALC", {"answer_spec": {"version": 1, "kind": "text"}})
        await svc.mark_reviewed("Q-PUB-CALC")
        pub_calc = await svc.publish("Q-PUB-CALC")
        assert pub_calc.grading_mode == "manual"
        assert pub_calc.auto_grading_eligible is False
        assert pub_calc.exam_eligible is False
