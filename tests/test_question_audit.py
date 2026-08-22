"""P0-8 正式题目状态审计测试（question_audit_logs）。"""

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, QuestionAuditLog
from app.services.content_review import ContentReviewService
from app.services.knowledge_seed import seed_phase_one_calculus
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


async def _import_choice():
    """导入一道 choice draft（可审核）。"""
    from app.data.database import get_db_session
    async with get_db_session() as db:
        await seed_phase_one_calculus(db)
        await db.commit()
    r = await QuestionImporter().import_from_dict_list([
        {
            "id": "Q-AUDIT-1", "category": "高数", "content": "1+1=?",
            "question_type": "choice",
            "options": [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}],
            "answer": "A", "analysis": "2",
            "knowledge_point_codes": ["function-definition"],
        }
    ])
    assert r.failed == 0


async def _audit_rows(qid: str) -> list:
    from app.data.database import get_db_session
    async with get_db_session() as db:
        rows = (
            await db.execute(
                select(QuestionAuditLog)
                .where(QuestionAuditLog.question_id == qid)
                .order_by(QuestionAuditLog.id)
            )
        ).scalars().all()
        return list(rows)


class TestQuestionAudit:
    pytestmark = pytest.mark.asyncio

    async def test_review_and_publish_record_operator(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _import_choice()
        svc = ContentReviewService()
        await svc.update_question(
            "Q-AUDIT-1", {"answer_spec": {"version": 1, "kind": "choice", "correct": "A"}}
        )
        await svc.mark_reviewed("Q-AUDIT-1", operator_id="admin-1")
        await svc.publish("Q-AUDIT-1", operator_id="admin-2")

        rows = await _audit_rows("Q-AUDIT-1")
        assert [r.action for r in rows] == ["reviewed", "published"]
        assert rows[0].from_status == "draft" and rows[0].to_status == "reviewed"
        assert rows[0].operator_id == "admin-1"
        assert rows[1].from_status == "reviewed" and rows[1].to_status == "published"
        assert rows[1].operator_id == "admin-2"

    async def test_publish_audit_carries_capability_details(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _import_choice()
        svc = ContentReviewService()
        await svc.update_question(
            "Q-AUDIT-1", {"answer_spec": {"version": 1, "kind": "choice", "correct": "A"}}
        )
        await svc.mark_reviewed("Q-AUDIT-1")
        await svc.publish("Q-AUDIT-1", operator_id="admin-2")

        rows = await _audit_rows("Q-AUDIT-1")
        pub = rows[-1]
        assert pub.details == {
            "grading_mode": "deterministic",
            "exam_eligible": True,
            "auto_grading_eligible": True,
        }

    async def test_batch_publish_records_operator_on_all_rows(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _import_choice()
        svc = ContentReviewService()
        await svc.update_question(
            "Q-AUDIT-1", {"answer_spec": {"version": 1, "kind": "choice", "correct": "A"}}
        )
        result = await svc.batch_publish(["Q-AUDIT-1"], operator_id="admin-9")
        assert result["published"] == ["Q-AUDIT-1"]

        rows = await _audit_rows("Q-AUDIT-1")
        assert [r.action for r in rows] == ["reviewed", "published"]
        assert all(r.operator_id == "admin-9" for r in rows)
