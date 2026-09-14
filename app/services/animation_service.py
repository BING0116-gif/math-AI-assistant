"""Owner-scoped persistence boundary for T15; no route or renderer is enabled yet."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.data.models import AnimationJob, AnimationJobEvent


class AnimationServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_request_fingerprint(*, template_id: str, trigger: str, visual_spec: dict[str, Any],
                                  template_source_sha256: str, renderer_image_digest: str,
                                  policy_version: str) -> str:
    payload = {
        "policy_version": policy_version,
        "renderer_image_digest": renderer_image_digest,
        "template_id": template_id,
        "template_source_sha256": template_source_sha256,
        "trigger": trigger,
        "visual_spec": visual_spec,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _owner_job_statement(user_id: str, job_id: str):
    return select(AnimationJob).where(
        AnimationJob.id == job_id,
        AnimationJob.user_id == user_id,
    ).options(selectinload(AnimationJob.artifacts))


async def get_animation_job(db: AsyncSession, *, user_id: str, job_id: str) -> AnimationJob:
    job = await db.scalar(_owner_job_statement(user_id, job_id))
    if job is None:
        raise AnimationServiceError("ANIMATION_JOB_NOT_FOUND", "动画任务不存在")
    return job


async def enqueue_validated_animation(
    db: AsyncSession,
    *,
    user_id: str,
    idempotency_key: str,
    template_id: str,
    trigger: str,
    visual_spec: dict[str, Any],
    admission_snapshot: dict[str, Any],
    template_source_sha256: str,
    renderer_image_digest: str,
    policy_version: str,
) -> AnimationJob:
    """Persist an already T08-verified request and its initial event atomically.

    This internal boundary intentionally refuses work while the feature flag is off.
    Public schemas cannot select ``teaching_strategy``; a future trusted caller may.
    """
    if not settings.MATH_ANIMATION_ENABLED:
        raise AnimationServiceError("ANIMATION_DISABLED", "动画功能尚未启用")
    if not user_id:
        raise AnimationServiceError("UNAUTHENTICATED", "缺少用户身份")
    if trigger not in {"user_explicit", "teaching_strategy"}:
        raise AnimationServiceError("VALIDATION_FAILED", "动画触发来源无效")

    fingerprint = canonical_request_fingerprint(
        template_id=template_id,
        trigger=trigger,
        visual_spec=visual_spec,
        template_source_sha256=template_source_sha256,
        renderer_image_digest=renderer_image_digest,
        policy_version=policy_version,
    )
    prior = await db.scalar(select(AnimationJob).where(
        AnimationJob.user_id == user_id,
        AnimationJob.idempotency_key == idempotency_key,
    ))
    if prior is not None:
        if prior.request_fingerprint != fingerprint:
            raise AnimationServiceError("IDEMPOTENCY_CONFLICT", "该幂等键已用于不同的动画请求")
        return prior

    job = AnimationJob(
        user_id=user_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        template_id=template_id,
        template_source_sha256=template_source_sha256,
        renderer_image_digest=renderer_image_digest,
        trigger=trigger,
        admission_snapshot=dict(admission_snapshot),
        visual_spec_snapshot=dict(visual_spec),
        max_attempts=settings.ANIMATION_MAX_ATTEMPTS,
    )
    db.add(job)
    await db.flush()
    db.add(AnimationJobEvent(
        event_id=str(uuid.uuid4()),
        job_id=job.id,
        sequence=1,
        event_type="job_created",
        stage="queued",
        status="pending",
        details={"trigger": trigger, "policy_version": policy_version},
    ))
    await db.flush()
    return job
