"""学生端组卷测试 API 测试（generate / submit 判分 / 配额 / 答案不泄漏）。"""

import pytest
from types import SimpleNamespace
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.paper_student_api import generate_paper, submit_paper
from app.data.models import (
    Base,
    KnowledgeGraphVersion,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
)
from app.services.knowledge_seed import seed_phase_one_calculus


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


def _req():
    return SimpleNamespace(state=SimpleNamespace(user_id="stu-1"))


async def seed_scope():
    from app.data.database import get_db_session
    async with get_db_session() as db:
        await seed_phase_one_calculus(db)
        await db.commit()
    async with get_db_session() as db:
        version = (await db.execute(select(KnowledgeGraphVersion).limit(1))).scalar_one()
        kp = (await db.execute(select(KnowledgePoint).limit(1))).scalar_one()
        return version.course_id, version.id, kp.id


async def add_question(db, qid, qtype, *, spec, answer, version_id, course_id, kp_id):
    q = Question(
        id=qid, content=f"题干 {qid}", question_type=qtype,
        options=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
        answer=answer, analysis="解析", category="高数", difficulty=2,
        review_status="published", grading_mode="deterministic",
        practice_eligible=True, exam_eligible=True, auto_grading_eligible=True,
        version_id=version_id, course_id=course_id, answer_spec=spec,
    )
    db.add(q)
    await db.flush()
    db.add(QuestionKnowledgePoint(question_id=q.id, knowledge_point_id=kp_id, is_primary=True))
    return q


async def seed_bank():
    course_id, version_id, kp_id = await seed_scope()
    from app.data.database import get_db_session
    async with get_db_session() as db:
        await add_question(db, "Q-CHOICE", "choice",
                           spec={"version": 1, "kind": "choice", "correct": "B"}, answer="B",
                           version_id=version_id, course_id=course_id, kp_id=kp_id)
        await add_question(db, "Q-NUM", "numeric_fill",
                           spec={"version": 1, "kind": "numeric_fill", "value": 3.5}, answer="3.5",
                           version_id=version_id, course_id=course_id, kp_id=kp_id)
        await add_question(db, "Q-JUDGE", "judge",
                           spec={"version": 1, "kind": "judge", "correct": True}, answer="true",
                           version_id=version_id, course_id=course_id, kp_id=kp_id)
        await add_question(db, "Q-EXPR", "expression_fill",
                           spec={"version": 1, "kind": "expression_fill", "canonical": "x**2 - 1", "variables": ["x"]},
                           answer="x^2-1", version_id=version_id, course_id=course_id, kp_id=kp_id)
        await db.commit()
    return version_id


class TestStudentPaper:
    pytestmark = pytest.mark.asyncio

    async def test_generate_strips_answers(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await seed_bank()
        resp = await generate_paper(_req(), {
            "config": {"type_mix": {"choice": 1, "numeric_fill": 1}, "random_seed": 1, "version_id": version_id},
            "title": "随堂练习",
        })
        data = resp["data"]
        assert data["total"] == 2
        assert data["title"] == "随堂练习"
        for q in data["questions"]:
            assert "answer_spec" not in q, "答案规范不得下发到学生端"
            assert "analysis" not in q
            assert q["content"] and "options" in q

    async def test_submit_grades_all_kinds(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await seed_bank()
        resp = await generate_paper(_req(), {
            "config": {"type_mix": {"choice": 1, "numeric_fill": 1, "judge": 1, "expression_fill": 1},
                       "random_seed": 3, "version_id": version_id},
        })
        questions = resp["data"]["questions"]
        answers = {}
        for q in questions:
            if q["question_type"] == "choice":
                answers[q["question_id"]] = "B"
            elif q["question_type"] == "numeric_fill":
                answers[q["question_id"]] = "3.5"
            elif q["question_type"] == "judge":
                answers[q["question_id"]] = "对"
            elif q["question_type"] == "expression_fill":
                answers[q["question_id"]] = "x*x - 1"
        result = (await submit_paper(_req(), resp["data"]["paper_id"], {"answers": answers}))["data"]
        assert result["total"] == 4
        assert result["correct"] == 4
        assert result["score"] == result["max_score"]
        assert all(r["correct"] for r in result["results"])

    async def test_wrong_answers_scored(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await seed_bank()
        resp = await generate_paper(_req(), {
            "config": {"type_mix": {"choice": 1, "numeric_fill": 1}, "random_seed": 1, "version_id": version_id},
        })
        questions = resp["data"]["questions"]
        answers = {questions[0]["question_id"]: "A", questions[1]["question_id"]: "999"}
        result = (await submit_paper(_req(), resp["data"]["paper_id"], {"answers": answers}))["data"]
        assert result["correct"] == 0
        assert result["score"] == 0
        # 提交后展示正确答案与解析
        for r in result["results"]:
            assert r["correct_answer"]
            assert r["your_answer"] != "（未作答）"

    async def test_unanswered_marked(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        version_id = await seed_bank()
        resp = await generate_paper(_req(), {
            "config": {"type_mix": {"choice": 1}, "random_seed": 1, "version_id": version_id},
        })
        result = (await submit_paper(_req(), resp["data"]["paper_id"], {"answers": {}}))["data"]
        assert result["correct"] == 0
        assert result["results"][0]["your_answer"] == "（未作答）"

    async def test_total_cap_rejected(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await generate_paper(_req(), {"config": {"type_mix": {"choice": 51}}})
        assert exc.value.status_code == 400
