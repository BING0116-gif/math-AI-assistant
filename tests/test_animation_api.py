from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.animation_api as animation_api
import app.data.database as database
from app.api.animation_api import router
from app.config.settings import settings
from app.data.models import AnimationJob, AnimationJobEvent, Base, User
from app.services.math_visualizer import mock_visual_spec


def _test_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_identity(request: Request, call_next):
        if value := request.headers.get("x-test-user"):
            request.state.user_id = value
        return await call_next(request)

    app.include_router(router)
    return app


def _body(key: str = "animation-api-0001") -> dict:
    return {
        "idempotency_key": key,
        "template_id": "secant_to_tangent",
        "trigger": "user_explicit",
        "visual_spec": mock_visual_spec("tangent_line"),
    }


@pytest.mark.asyncio
async def test_all_animation_routes_require_identity():
    async with AsyncClient(transport=ASGITransport(app=_test_app()), base_url="http://test") as client:
        assert (await client.post("/api/animations/jobs", json=_body())).status_code == 401
        assert (await client.get("/api/animations/jobs/missing")).status_code == 401
        assert (await client.post("/api/animations/jobs/missing/cancel")).status_code == 401


@pytest.mark.asyncio
async def test_disabled_create_fails_before_validation_or_database(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", False)

    def forbidden_validation(**kwargs):
        raise AssertionError("T08 validation must not run while disabled")

    def forbidden_database():
        raise AssertionError("database session must not open while disabled")

    monkeypatch.setattr(animation_api, "validate_public_animation_request", forbidden_validation)
    monkeypatch.setattr(animation_api, "get_db_session", forbidden_database)
    async with AsyncClient(transport=ASGITransport(app=_test_app()), base_url="http://test") as client:
        response = await client.post("/api/animations/jobs", json=_body(), headers={"x-test-user": "owner-a"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ANIMATION_DISABLED"


@pytest.mark.asyncio
async def test_create_status_cancel_and_cross_owner_hiding(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    monkeypatch.setattr(settings, "ANIMATION_RENDERER_IMAGE", "sha256:" + "b" * 64)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="owner-a", username="api-a", email="api-a@example.test", password_hash="x"),
            User(id="owner-b", username="api-b", email="api-b@example.test", password_hash="x"),
        ])
        await db.commit()

    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/animations/jobs", json=_body(), headers={"x-test-user": "owner-a"})
        assert created.status_code == 202
        payload = created.json()
        assert payload["code"] == 0 and payload["message"] == "ok"
        assert payload["data"]["status"] == "pending"
        assert payload["data"]["stage"] == "queued"
        assert payload["data"]["artifacts"] == []
        assert not ({"user_id", "storage_key", "worker_id", "lease_expires_at"} & payload["data"].keys())
        job_id = payload["data"]["job_id"]

        own = await client.get(f"/api/animations/jobs/{job_id}", headers={"x-test-user": "owner-a"})
        foreign_get = await client.get(f"/api/animations/jobs/{job_id}", headers={"x-test-user": "owner-b"})
        foreign_cancel = await client.post(f"/api/animations/jobs/{job_id}/cancel", headers={"x-test-user": "owner-b"})
        missing = await client.get("/api/animations/jobs/does-not-exist", headers={"x-test-user": "owner-b"})
        assert own.status_code == 200
        for hidden in (foreign_get, foreign_cancel, missing):
            assert hidden.status_code == 404
            assert hidden.json()["detail"]["code"] == "ANIMATION_JOB_NOT_FOUND"

        cancelled = await client.post(f"/api/animations/jobs/{job_id}/cancel", headers={"x-test-user": "owner-a"})
        repeated = await client.post(f"/api/animations/jobs/{job_id}/cancel", headers={"x-test-user": "owner-a"})
        assert cancelled.json()["data"]["status"] == repeated.json()["data"]["status"] == "cancelled"

    async with factory() as db:
        assert await db.scalar(select(func.count(AnimationJob.id))) == 1
        assert await db.scalar(select(func.count(AnimationJobEvent.id))) == 2
    await engine.dispose()
