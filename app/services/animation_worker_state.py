"""Transactional SQL state machine for a future dedicated animation worker.

This module does not start a worker and never invokes Docker, Manim or a model API.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.data.models import AnimationArtifact, AnimationJob, AnimationJobEvent
from app.services.animation_service import AnimationServiceError
from app.services.animation_storage import ValidatedArtifact

TerminalStatus = Literal["succeeded", "fallback", "failed", "cancelled"]
_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,35}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,49}$")


@dataclass(frozen=True)
class HeartbeatResult:
    accepted: bool
    cancel_requested: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_worker_id(worker_id: str) -> None:
    if not _WORKER_ID.fullmatch(worker_id):
        raise AnimationServiceError("WORKER_ID_INVALID", "动画 worker 标识无效")


def _validate_event_id(event_id: str) -> None:
    if not _EVENT_ID.fullmatch(event_id):
        raise AnimationServiceError("EVENT_ID_INVALID", "动画事件标识无效")


def _lease_duration(value: int | None) -> int:
    resolved = settings.ANIMATION_JOB_LEASE_SECONDS if value is None else value
    if not 10 <= resolved <= 600:
        raise AnimationServiceError("LEASE_INVALID", "动画任务租约必须在 10 到 600 秒之间")
    return resolved


def _aware_now(value: datetime | None) -> datetime:
    resolved = value or _utc_now()
    if resolved.tzinfo is None:
        raise AnimationServiceError("CLOCK_INVALID", "动画任务时钟必须包含时区")
    return resolved.astimezone(timezone.utc)


async def _locked_job(db: AsyncSession, job_id: str) -> AnimationJob | None:
    return await db.scalar(
        select(AnimationJob).where(AnimationJob.id == job_id).with_for_update()
    )


async def _replayed_event(db: AsyncSession, event_id: str, job_id: str) -> bool:
    existing_job_id = await db.scalar(
        select(AnimationJobEvent.job_id).where(AnimationJobEvent.event_id == event_id)
    )
    if existing_job_id is None:
        return False
    if existing_job_id != job_id:
        raise AnimationServiceError("EVENT_ID_CONFLICT", "动画事件标识已用于其他任务")
    return True


async def _append_event(
    db: AsyncSession,
    job: AnimationJob,
    *,
    event_id: str,
    event_type: str,
    details: dict | None = None,
) -> None:
    sequence = await db.scalar(
        select(func.max(AnimationJobEvent.sequence)).where(AnimationJobEvent.job_id == job.id)
    )
    db.add(AnimationJobEvent(
        event_id=event_id,
        job_id=job.id,
        sequence=(sequence or 0) + 1,
        event_type=event_type,
        stage=job.stage,
        status=job.status,
        details=dict(details or {}),
    ))


async def claim_next_animation_job(
    db: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
    now: datetime | None = None,
) -> AnimationJob | None:
    """Claim one pending or lease-expired job with PostgreSQL row locking."""
    if not settings.MATH_ANIMATION_ENABLED:
        return None
    _validate_worker_id(worker_id)
    lease_seconds = _lease_duration(lease_seconds)
    now = _aware_now(now)
    statement = (
        select(AnimationJob)
        .where(
            AnimationJob.cancel_requested.is_(False),
            or_(
                AnimationJob.status == "pending",
                (AnimationJob.status == "running") & (AnimationJob.lease_expires_at < now),
            ),
        )
        .order_by(AnimationJob.created_at, AnimationJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = await db.scalar(statement)
    if job is None:
        return None

    recovered = job.status == "running"
    job.status = "running"
    job.stage = "recovered" if recovered else "claimed"
    job.worker_id = worker_id
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.started_at = job.started_at or now
    job.updated_at = now
    if recovered:
        job.recovery_count += 1
    await _append_event(
        db,
        job,
        event_id=str(uuid.uuid4()),
        event_type="job_recovered" if recovered else "job_claimed",
        details={"recovery_count": job.recovery_count},
    )
    await db.flush()
    return job


async def heartbeat_animation_job(
    db: AsyncSession,
    *,
    job_id: str,
    worker_id: str,
    lease_seconds: int | None = None,
    now: datetime | None = None,
) -> HeartbeatResult:
    _validate_worker_id(worker_id)
    lease_seconds = _lease_duration(lease_seconds)
    job = await _locked_job(db, job_id)
    if job is None or job.status != "running" or job.worker_id != worker_id:
        return HeartbeatResult(accepted=False)
    if job.cancel_requested:
        return HeartbeatResult(accepted=True, cancel_requested=True)
    now = _aware_now(now)
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.updated_at = now
    await db.flush()
    return HeartbeatResult(accepted=True)


async def begin_animation_attempt(
    db: AsyncSession,
    *,
    job_id: str,
    worker_id: str,
    event_id: str,
) -> AnimationJob | None:
    """Increment the render count exactly once immediately before an attempt."""
    _validate_worker_id(worker_id)
    _validate_event_id(event_id)
    job = await _locked_job(db, job_id)
    if await _replayed_event(db, event_id, job_id):
        return job
    if (
        job is None
        or job.status != "running"
        or job.worker_id != worker_id
        or job.cancel_requested
        or job.attempt_count >= job.max_attempts
    ):
        return None
    job.attempt_count += 1
    job.stage = "rendering"
    job.updated_at = _utc_now()
    await _append_event(
        db,
        job,
        event_id=event_id,
        event_type="render_attempt_started",
        details={"attempt": job.attempt_count},
    )
    await db.flush()
    return job


async def finish_animation_job(
    db: AsyncSession,
    *,
    job_id: str,
    worker_id: str,
    event_id: str,
    artifact: ValidatedArtifact | None = None,
) -> AnimationJob | None:
    """Commit success unless cancellation already won the locked-row race."""
    _validate_worker_id(worker_id)
    _validate_event_id(event_id)
    job = await _locked_job(db, job_id)
    if await _replayed_event(db, event_id, job_id):
        return job
    if (
        job is None
        or job.status != "running"
        or (job.stage != "rendering" and not job.cancel_requested)
        or job.attempt_count < 1
        or job.worker_id != worker_id
    ):
        return None
    now = _utc_now()
    if job.cancel_requested:
        job.status = "cancelled"
        job.stage = "cancelled"
        event_type = "job_cancelled"
    else:
        if artifact is None:
            return None
        job.status = "succeeded"
        job.stage = "completed"
        event_type = "job_succeeded"
        db.add(AnimationArtifact(
            job_id=job.id,
            user_id=job.user_id,
            kind="video",
            storage_key=artifact.storage_key,
            mime_type=artifact.mime_type,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            validation_status="validated",
            published_at=now,
        ))
    job.worker_id = None
    job.heartbeat_at = None
    job.lease_expires_at = None
    job.completed_at = now
    job.updated_at = now
    await _append_event(db, job, event_id=event_id, event_type=event_type)
    await db.flush()
    return job


async def fail_animation_attempt(
    db: AsyncSession,
    *,
    job_id: str,
    worker_id: str,
    event_id: str,
    error_code: str,
) -> AnimationJob | None:
    """Requeue once, then use deterministic T08 static fallback."""
    _validate_worker_id(worker_id)
    _validate_event_id(event_id)
    if not _ERROR_CODE.fullmatch(error_code):
        raise AnimationServiceError("ERROR_CODE_INVALID", "动画失败代码无效")
    job = await _locked_job(db, job_id)
    if await _replayed_event(db, event_id, job_id):
        return job
    if (
        job is None
        or job.status != "running"
        or (job.stage != "rendering" and not job.cancel_requested)
        or job.attempt_count < 1
        or job.worker_id != worker_id
    ):
        return None

    now = _utc_now()
    if job.cancel_requested:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.completed_at = now
        event_type = "job_cancelled"
    elif job.attempt_count < job.max_attempts:
        job.status = "pending"
        job.stage = "retry_queued"
        event_type = "render_attempt_failed"
    else:
        job.status = "fallback"
        job.stage = "fallback"
        job.fallback_kind = "t08_static"
        job.error_code = error_code
        job.error_message = "动画生成失败，已回退到静态可视化"
        job.completed_at = now
        event_type = "job_fallback"
    job.worker_id = None
    job.heartbeat_at = None
    job.lease_expires_at = None
    job.updated_at = now
    await _append_event(
        db,
        job,
        event_id=event_id,
        event_type=event_type,
        details={"attempt": job.attempt_count, "error_code": error_code},
    )
    await db.flush()
    return job
