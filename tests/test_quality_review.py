import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import AIInteractionRun, Base, User
from app.services.quality_review import list_review_queue, submit_review


@pytest.mark.asyncio
async def test_quality_queue_is_redacted_prioritized_and_review_is_idempotent(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="student-q", username="student-q", email="student-q@example.test", password_hash="x"))
        await db.flush()
        db.add_all([
            AIInteractionRun(id="run-warn", user_id="student-q", request_kind="tutor", status="completed", quality_sampled=True, critic_verdict="warn", critic_issues=[{"code": "gap", "detail": "private"}]),
            AIInteractionRun(id="run-fail", user_id="student-q", request_kind="tutor", status="completed", quality_sampled=True, critic_verdict="fail", critic_issues=[{"code": "unsafe", "detail": "private"}]),
        ])
        await db.commit()
    queue = await list_review_queue()
    assert queue["total"] == 2
    assert queue["items"][0]["run_id"] == "run-fail"
    assert queue["items"][0]["critic_issues"] == [{"code": "unsafe"}]
    result = await submit_review(run_id="run-fail", reviewer_id="admin-1", verdict="fail", issue_codes=["unsafe"])
    assert result["review_verdict"] == "fail"
    await submit_review(run_id="run-fail", reviewer_id="admin-1", verdict="fail", issue_codes=["unsafe"])
    pending = await list_review_queue()
    assert pending["total"] == 1 and pending["items"][0]["run_id"] == "run-warn"
    await engine.dispose()
