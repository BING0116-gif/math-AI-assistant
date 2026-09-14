import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import AnimationArtifact, AnimationJob, AnimationJobEvent, Base, User
from app.schemas.animation import CreateAnimationJobRequest
from app.services.animation_service import AnimationServiceError, enqueue_validated_animation, get_animation_job


def test_public_schema_rejects_internal_or_executable_fields():
    valid = {
        "idempotency_key": "animation-0001",
        "template_id": "secant_to_tangent",
        "visual_spec": {"type": "tangent_line"},
    }
    assert CreateAnimationJobRequest.model_validate(valid).trigger == "user_explicit"
    for extra in ({"trigger": "teaching_strategy"}, {"user_id": "other"}, {"python": "print(1)"}):
        with pytest.raises(ValidationError):
            CreateAnimationJobRequest.model_validate(valid | extra)


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
