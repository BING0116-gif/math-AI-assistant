"""Owner-scoped persistence and state boundary for the T15 production API."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.data.models import AnimationJob, AnimationJobEvent
from app.schemas.animation import AnimationArtifactSummary, AnimationJobResponse


class AnimationServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_PUBLIC_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,49}$")
_SENSITIVE_ERROR = re.compile(
    r"(?:stderr|traceback|(?:api[_-]?key|token|secret|password)\s*[=:]|"
    r"[A-Za-z]:[\\/]|(?:^|\s)/(?:home|root|tmp|var|etc|app|workspace)/)",
    re.IGNORECASE,
)


def _public_error(code: str | None, message: str | None) -> tuple[str | None, str | None]:
    if code is not None and not _PUBLIC_ERROR_CODE.fullmatch(code):
        code = "ANIMATION_FAILED"
    if message is not None:
        message = " ".join(message.split())[:500]
        if _SENSITIVE_ERROR.search(message):
            message = "动画生成失败，请稍后重试"
    return code, message


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


def animation_job_response(job: AnimationJob) -> AnimationJobResponse:
    """Build the public projection without leaking owner, storage or worker data."""
    artifacts: list[AnimationArtifactSummary] = []
    if job.status == "succeeded":
        artifacts = [
            AnimationArtifactSummary.model_validate(artifact, from_attributes=True)
            for artifact in job.artifacts
            if artifact.validation_status == "validated" and artifact.published_at is not None
        ]
    error_code, error_message = _public_error(job.error_code, job.error_message)
    return AnimationJobResponse(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        template_id=job.template_id,
        attempt_count=job.attempt_count,
        fallback_kind=job.fallback_kind,
        error_code=error_code,
        error_message=error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        artifacts=artifacts,
    )


async def cancel_animation_job(db: AsyncSession, *, user_id: str, job_id: str) -> AnimationJob:
    """Request cancellation using an owner-scoped lookup; repeated calls are safe."""
    job = await db.scalar(
        select(AnimationJob).where(
            AnimationJob.id == job_id,
            AnimationJob.user_id == user_id,
        ).with_for_update()
    )
    if job is None:
        raise AnimationServiceError("ANIMATION_JOB_NOT_FOUND", "动画任务不存在")
    if job.status in {"succeeded", "fallback", "failed", "cancelled"} or job.cancel_requested:
        await db.refresh(job, attribute_names=["artifacts"])
        return job

    now = datetime.now(timezone.utc)
    job.cancel_requested = True
    event_type = "cancel_requested"
    if job.status == "pending":
        job.status = "cancelled"
        job.stage = "cancelled"
        job.completed_at = now
        event_type = "job_cancelled"
    else:
        job.stage = "cancel_requested"
    job.updated_at = now

    last_sequence = await db.scalar(
        select(func.max(AnimationJobEvent.sequence)).where(AnimationJobEvent.job_id == job.id)
    )
    db.add(AnimationJobEvent(
        event_id=str(uuid.uuid4()),
        job_id=job.id,
        sequence=(last_sequence or 0) + 1,
        event_type=event_type,
        stage=job.stage,
        status=job.status,
        details={},
    ))
    await db.flush()
    await db.refresh(job, attribute_names=["artifacts"])
    return job


def validate_public_animation_request(*, template_id: str, visual_spec: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run the approved T08/fixed-template admission without invoking a renderer."""
    from ops.math_animator_poc.tracer.registry import TEMPLATES, verify_trusted_source
    from ops.math_animator_poc.tracer.visual_adapter import adapt_math_visual_spec

    animation_spec = adapt_math_visual_spec(visual_spec, template_id)
    definition = TEMPLATES[animation_spec.template_id]
    source_hash = verify_trusted_source(definition).lower()
    return {
        "verified": True,
        "adapter": "t08_fixed_template_v1",
        "animation_schema_version": animation_spec.schema_version,
    }, source_hash


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
