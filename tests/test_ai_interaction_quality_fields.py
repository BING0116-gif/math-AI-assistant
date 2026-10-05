import asyncio

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import AIInteractionRun, Base, ChatSession, User
from app.services.tutor_service import complete_ai_run, mark_ai_run_modified, start_ai_run


@pytest.mark.asyncio
async def test_quality_metadata_is_persisted_and_metrics_are_emitted(monkeypatch):
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
        db.add(User(id="quality-user", username="quality", email="quality@example.test", password_hash="x"))
        await db.flush()
        db.add(AIInteractionRun(id="quality-run", user_id="quality-user", request_kind="tutor", status="started"))
        await db.commit()

    await complete_ai_run(
        "quality-run",
        status="completed",
        metadata={
            "critic_verdict": "warn",
            "critic_issues": [{"code": "missing_step", "detail": "redacted"}],
            "quality_sampled": True,
            "review_verdict": "pass",
            "reviewer_id": "reviewer-1",
            "followup_count": 2,
            "modified_by_user": True,
        },
    )
    async with factory() as db:
        run = await db.scalar(select(AIInteractionRun).where(AIInteractionRun.id == "quality-run"))
        assert run.critic_verdict == "warn"
        assert run.critic_issues == [{"code": "missing_step", "detail": "redacted"}]
        assert run.quality_sampled is True
        assert run.review_verdict == "pass"
        assert run.reviewer_id == "reviewer-1"
        assert run.followup_count == 2
        assert run.modified_by_user is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_followup_and_modified_signal_are_owner_scoped_and_idempotent(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="owner-a", username="owner-a", email="a@example.test", password_hash="x"),
            User(id="owner-b", username="owner-b", email="b@example.test", password_hash="x"),
            ChatSession(id="chat-owner-a", user_id="owner-a", external_session_id="ext-a"),
        ])
        await db.commit()

    first = await start_ai_run("owner-a", "chat-owner-a", "guided", {})
    second = await start_ai_run("owner-a", "chat-owner-a", "guided", {})
    assert await mark_ai_run_modified("owner-b", first) is False
    assert await mark_ai_run_modified("owner-a", first) is True
    assert await mark_ai_run_modified("owner-a", first) is True
    async with factory() as db:
        original = await db.get(AIInteractionRun, first)
        assert original.followup_count == 1
        assert original.modified_by_user is True
        assert (await db.get(AIInteractionRun, second)).followup_count == 0
    await engine.dispose()
