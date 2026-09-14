from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import AnimationJob, AnimationJobEvent, Base, User
from app.services.animation_service import enqueue_validated_animation
from app.services.animation_worker_state import (
    begin_animation_attempt,
    claim_next_animation_job,
    fail_animation_attempt,
    finish_animation_job,
    heartbeat_animation_job,
)


@pytest_asyncio.fixture
async def worker_db(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", True)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(User(id="worker-owner", username="worker-owner", email="worker@example.test", password_hash="x"))
        await db.flush()
        yield db
    await engine.dispose()


async def _enqueue(db, key: str) -> AnimationJob:
    return await enqueue_validated_animation(
        db,
        user_id="worker-owner",
        idempotency_key=key,
        template_id="secant_to_tangent",
        trigger="user_explicit",
        visual_spec={"type": "tangent_line"},
        admission_snapshot={"verified": True},
        template_source_sha256="a" * 64,
        renderer_image_digest="sha256:" + "b" * 64,
        policy_version="t15-v1",
    )


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_wrong_worker_cannot_advance(worker_db):
    job = await _enqueue(worker_db, "worker-claim-0001")
    claimed = await claim_next_animation_job(worker_db, worker_id="worker-a")
    assert claimed.id == job.id
    assert claimed.status == "running" and claimed.attempt_count == 0
    assert await claim_next_animation_job(worker_db, worker_id="worker-b") is None
    assert (await heartbeat_animation_job(
        worker_db, job_id=job.id, worker_id="worker-b"
    )).accepted is False
    assert await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-b", event_id="attempt-wrong-001"
    ) is None
    assert await finish_animation_job(
        worker_db, job_id=job.id, worker_id="worker-b", event_id="finish-wrong-001"
    ) is None


@pytest.mark.asyncio
async def test_expired_lease_recovery_preserves_attempt_count(worker_db):
    job = await _enqueue(worker_db, "worker-recover-01")
    claimed = await claim_next_animation_job(worker_db, worker_id="worker-a")
    await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="attempt-recover-1"
    )
    claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await worker_db.flush()

    recovered = await claim_next_animation_job(worker_db, worker_id="worker-b")
    assert recovered.id == job.id
    assert recovered.worker_id == "worker-b"
    assert recovered.recovery_count == 1
    assert recovered.attempt_count == 1


@pytest.mark.asyncio
async def test_failure_retries_once_then_falls_back_and_events_are_idempotent(worker_db):
    job = await _enqueue(worker_db, "worker-retry-0001")
    await claim_next_animation_job(worker_db, worker_id="worker-a")
    await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="attempt-retry-001"
    )
    retry = await fail_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-a",
        event_id="failure-retry-001", error_code="RENDER_TIMEOUT",
    )
    assert retry.status == "pending" and retry.stage == "retry_queued"

    await claim_next_animation_job(worker_db, worker_id="worker-b")
    await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-b", event_id="attempt-retry-002"
    )
    fallback = await fail_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-b",
        event_id="failure-retry-002", error_code="RENDER_TIMEOUT",
    )
    replay = await fail_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-b",
        event_id="failure-retry-002", error_code="RENDER_TIMEOUT",
    )
    assert fallback.status == replay.status == "fallback"
    assert fallback.fallback_kind == "t08_static"
    assert fallback.attempt_count == 2
    assert await claim_next_animation_job(worker_db, worker_id="worker-c") is None
    assert await worker_db.scalar(select(func.count(AnimationJobEvent.id))) == 7


@pytest.mark.asyncio
async def test_cancel_wins_over_late_success(worker_db):
    from app.services.animation_service import cancel_animation_job

    job = await _enqueue(worker_db, "worker-cancel-001")
    await claim_next_animation_job(worker_db, worker_id="worker-a")
    await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="attempt-cancel-01"
    )
    await cancel_animation_job(worker_db, user_id="worker-owner", job_id=job.id)
    beat = await heartbeat_animation_job(worker_db, job_id=job.id, worker_id="worker-a")
    assert beat.accepted and beat.cancel_requested
    finished = await finish_animation_job(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="finish-cancel-001"
    )
    assert finished.status == "cancelled"
    assert finished.stage == "cancelled"


@pytest.mark.asyncio
async def test_success_completion_event_replay_does_not_transition_twice(worker_db):
    job = await _enqueue(worker_db, "worker-success-001")
    await claim_next_animation_job(worker_db, worker_id="worker-a")
    await begin_animation_attempt(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="attempt-success-01"
    )
    first = await finish_animation_job(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="finish-success-001"
    )
    replay = await finish_animation_job(
        worker_db, job_id=job.id, worker_id="worker-a", event_id="finish-success-001"
    )
    assert first.status == replay.status == "succeeded"
    assert await worker_db.scalar(select(func.count(AnimationJobEvent.id))) == 4


@pytest.mark.asyncio
async def test_disabled_claim_returns_before_query(monkeypatch):
    monkeypatch.setattr(settings, "MATH_ANIMATION_ENABLED", False)

    class NoDatabase:
        def scalar(self, *args, **kwargs):
            raise AssertionError("disabled worker gate must not query SQL")

    assert await claim_next_animation_job(NoDatabase(), worker_id="worker-a") is None
