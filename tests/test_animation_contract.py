import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import AnimationArtifact, AnimationJob, AnimationJobEvent, Base, User
from app.schemas.animation import CreateAnimationJobRequest
from app.services.animation_service import (
    AnimationServiceError,
    animation_job_response,
    cancel_animation_job,
    enqueue_validated_animation,
    get_animation_job,
)


def test_public_schema_rejects_internal_or_executable_fields():
    valid = {
        "idempotency_key": "animation-0001",
        "template_id": "secant_to_tangent",
        "visual_spec": {"type": "tangent_line"},
    }
    assert CreateAnimationJobRequest.model_validate(valid).trigger == "user_explicit"
    forbidden = (
        {"trigger": "teaching_strategy"}, {"user_id": "other"}, {"teaching_strategy": {}},
        {"teaching_score": 1}, {"python": "print(1)"}, {"scene_name": "Scene"},
        {"local_path": "C:/secret"}, {"docker_args": ["--network=host"]},
        {"renderer_image": "evil"}, {"template_source_hash": "a" * 64},
    )
    for extra in forbidden:
        with pytest.raises(ValidationError):
            CreateAnimationJobRequest.model_validate(valid | extra)
    with pytest.raises(ValidationError):
        CreateAnimationJobRequest.model_validate(valid | {"visual_spec": {"x": math.nan}})


def test_animation_foreign_keys_are_owner_bound_and_cascading():
    job_user_fk = next(iter(AnimationJob.__table__.c.user_id.foreign_keys))
    artifact_user_fk = next(iter(AnimationArtifact.__table__.c.user_id.foreign_keys))
    artifact_job_fk = next(iter(AnimationArtifact.__table__.c.job_id.foreign_keys))
    assert (job_user_fk.target_fullname, job_user_fk.ondelete) == ("users.id", "CASCADE")
    assert (artifact_user_fk.target_fullname, artifact_user_fk.ondelete) == ("users.id", "CASCADE")
    assert (artifact_job_fk.target_fullname, artifact_job_fk.ondelete) == ("animation_jobs.id", "CASCADE")


@pytest.mark.asyncio
async def test_disabled_gate_runs_before_persistence():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        with pytest.raises(AnimationServiceError, match="尚未启用"):
            await enqueue_validated_animation(
                db, user_id="owner-a", idempotency_key="animation-0001",
                template_id="secant_to_tangent", trigger="user_explicit",
                visual_spec={"type": "tangent_line"}, admission_snapshot={"verified": True},
                template_source_sha256="a" * 64, renderer_image_digest="sha256:" + "b" * 64,
                policy_version="t15-v1",
            )
        assert await db.scalar(select(func.count(AnimationJob.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_running_cancel_requests_stop_and_terminal_job_is_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="owner-a", username="states-a", email="states-a@example.test", password_hash="x"))
        await db.flush()
        common = dict(
            db=db, user_id="owner-a", template_id="secant_to_tangent", trigger="user_explicit",
            visual_spec={"type": "tangent_line"}, admission_snapshot={"verified": True},
            template_source_sha256="a" * 64, renderer_image_digest="sha256:" + "b" * 64,
            policy_version="t15-v1",
        )
        running = await enqueue_validated_animation(idempotency_key="animation-running-01", **common)
        running.status = "running"
        running.stage = "rendering"
        await db.flush()
        requested = await cancel_animation_job(db, user_id="owner-a", job_id=running.id)
        assert requested.status == "running"
        assert requested.stage == "cancel_requested"
        assert requested.cancel_requested is True

        succeeded = await enqueue_validated_animation(idempotency_key="animation-success-01", **common)
        succeeded.status = "succeeded"
        succeeded.stage = "completed"
        await db.flush()
        unchanged = await cancel_animation_job(db, user_id="owner-a", job_id=succeeded.id)
        assert unchanged.status == "succeeded"
        assert unchanged.cancel_requested is False
        assert await db.scalar(select(func.count(AnimationJobEvent.id))) == 3
    await engine.dispose()


def test_public_response_sanitizes_internal_error_text():
    job = AnimationJob(
        id="job-1", user_id="owner-a", idempotency_key="animation-error-01",
        request_fingerprint="a" * 64, template_id="secant_to_tangent",
        template_source_sha256="b" * 64, renderer_image_digest="sha256:" + "c" * 64,
        trigger="user_explicit", admission_snapshot={}, visual_spec_snapshot={"type": "tangent_line"},
        status="failed", stage="failed", error_code="RENDER_FAILED",
        error_message="stderr: API_KEY=secret C:\\runtime\\animation.log",
        attempt_count=2, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    job.artifacts = []
    response = animation_job_response(job)
    assert response.error_code == "RENDER_FAILED"
    assert response.error_message == "动画生成失败，请稍后重试"


@pytest.mark.asyncio
async def test_cancel_is_owner_scoped_and_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="owner-a", username="cancel-a", email="cancel-a@example.test", password_hash="x"),
            User(id="owner-b", username="cancel-b", email="cancel-b@example.test", password_hash="x"),
        ])
        await db.flush()
        job = await enqueue_validated_animation(
            db, user_id="owner-a", idempotency_key="animation-cancel-0001",
            template_id="secant_to_tangent", trigger="user_explicit",
            visual_spec={"type": "tangent_line"}, admission_snapshot={"verified": True},
            template_source_sha256="a" * 64, renderer_image_digest="sha256:" + "b" * 64,
            policy_version="t15-v1",
        )
        with pytest.raises(AnimationServiceError) as hidden:
            await cancel_animation_job(db, user_id="owner-b", job_id=job.id)
        assert hidden.value.code == "ANIMATION_JOB_NOT_FOUND"

        cancelled = await cancel_animation_job(db, user_id="owner-a", job_id=job.id)
        repeated = await cancel_animation_job(db, user_id="owner-a", job_id=job.id)
        assert cancelled.status == repeated.status == "cancelled"
        assert cancelled.stage == "cancelled"
        assert await db.scalar(select(func.count(AnimationJobEvent.id))) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_scoped_idempotent_enqueue_and_lookup(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([
            User(id="owner-a", username="owner-a", email="owner-a@example.test", password_hash="x"),
            User(id="owner-b", username="owner-b", email="owner-b@example.test", password_hash="x"),
        ])
        await db.flush()
        args = dict(
            user_id="owner-a", idempotency_key="animation-0001",
            template_id="secant_to_tangent", trigger="user_explicit",
            visual_spec={"type": "tangent_line"}, admission_snapshot={"verified": True},
            template_source_sha256="a" * 64, renderer_image_digest="sha256:" + "b" * 64,
            policy_version="t15-v1",
        )
        first = await enqueue_validated_animation(db, **args)
        second = await enqueue_validated_animation(db, **args)
        assert first.id == second.id
        assert await db.scalar(select(func.count(AnimationJob.id))) == 1
        assert await db.scalar(select(func.count(AnimationJobEvent.id))) == 1
        assert (await get_animation_job(db, user_id="owner-a", job_id=first.id)).id == first.id
        with pytest.raises(AnimationServiceError) as hidden:
            await get_animation_job(db, user_id="owner-b", job_id=first.id)
        assert hidden.value.code == "ANIMATION_JOB_NOT_FOUND"
        with pytest.raises(AnimationServiceError) as conflict:
            await enqueue_validated_animation(db, **(args | {"visual_spec": {"type": "area"}}))
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    await engine.dispose()
