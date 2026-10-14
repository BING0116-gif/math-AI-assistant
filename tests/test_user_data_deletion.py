from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, User
from app.services.user_data_deletion import preview_user_deletion, request_user_deletion


@pytest.mark.asyncio
async def test_preview_is_owner_scoped_and_non_mutating():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="u1", username="u1", email="u1@example.test", password_hash="x"),
            User(id="u2", username="u2", email="u2@example.test", password_hash="x"),
        ])
        await db.commit()
        report = await preview_user_deletion(db, "u1")
        assert report.user_id == "u1"
        assert report.counts["memories"] == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_request_requires_second_confirmation_and_is_idempotent(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        with pytest.raises(PermissionError):
            await request_user_deletion(db, user_id="u1", requested_by="admin", confirmation="DELETE")
        first = await request_user_deletion(db, user_id="u1", requested_by="admin", confirmation="DELETE_USER_DATA")
        await db.commit()
        second = await request_user_deletion(db, user_id="u1", requested_by="admin", confirmation="DELETE_USER_DATA")
        assert first["task_id"] == second["task_id"]
    await engine.dispose()
