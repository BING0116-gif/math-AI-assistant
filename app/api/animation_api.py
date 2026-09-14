"""Authenticated, disabled-by-default production API for MathAnimator jobs."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.config.settings import settings
from app.data.database import get_db_session
from app.schemas.animation import AnimationJobResponse, CreateAnimationJobRequest
from app.services.animation_service import (
    AnimationServiceError,
    animation_job_response,
    cancel_animation_job,
    enqueue_validated_animation,
    get_animation_job,
    validate_public_animation_request,
)
from app.services.animation_storage import get_owner_artifact, iter_file_range, parse_byte_range

router = APIRouter(prefix="/api/animations", tags=["数学动画"])
_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def _user_id(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)


def _raise_service_error(error: AnimationServiceError) -> None:
    code_to_status = {
        "ANIMATION_DISABLED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "ANIMATION_JOB_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "IDEMPOTENCY_CONFLICT": status.HTTP_409_CONFLICT,
        "ANIMATION_ARTIFACT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "RANGE_NOT_SATISFIABLE": status.HTTP_416_RANGE_NOT_SATISFIABLE,
    }
    raise HTTPException(
        code_to_status.get(error.code, status.HTTP_422_UNPROCESSABLE_CONTENT),
        detail={"code": error.code, "message": error.message},
    )


def _disabled_gate() -> None:
    if not settings.MATH_ANIMATION_ENABLED:
        _raise_service_error(AnimationServiceError("ANIMATION_DISABLED", "动画功能尚未启用"))


def _renderer_digest() -> str:
    value = settings.ANIMATION_RENDERER_IMAGE.strip()
    if not _DIGEST.fullmatch(value):
        raise AnimationServiceError("ANIMATION_RENDERER_UNAVAILABLE", "动画渲染器尚未就绪")
    return value.lower()


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_animation_job(request: Request, body: CreateAnimationJobRequest):
    user_id = _user_id(request)
    _disabled_gate()
    try:
        admission, source_hash = validate_public_animation_request(
            template_id=body.template_id,
            visual_spec=body.visual_spec,
        )
        async with get_db_session() as db:
            job = await enqueue_validated_animation(
                db,
                user_id=user_id,
                idempotency_key=body.idempotency_key,
                template_id=body.template_id,
                trigger=body.trigger,
                visual_spec=body.visual_spec,
                admission_snapshot=admission,
                template_source_sha256=source_hash,
                renderer_image_digest=_renderer_digest(),
                policy_version="t15-production-v1",
            )
            await db.refresh(job, attribute_names=["artifacts"])
            data = animation_job_response(job)
        return {"code": 0, "data": data.model_dump(mode="json"), "message": "ok"}
    except AnimationServiceError as error:
        _raise_service_error(error)
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "ANIMATION_SPEC_INVALID", "message": str(error)},
        ) from error


@router.get("/jobs/{job_id}")
async def read_animation_job(request: Request, job_id: str):
    user_id = _user_id(request)
    try:
        async with get_db_session() as db:
            data = animation_job_response(await get_animation_job(db, user_id=user_id, job_id=job_id))
        return {"code": 0, "data": data.model_dump(mode="json"), "message": "ok"}
    except AnimationServiceError as error:
        _raise_service_error(error)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str):
    user_id = _user_id(request)
    try:
        async with get_db_session() as db:
            job = await cancel_animation_job(db, user_id=user_id, job_id=job_id)
            data = animation_job_response(job)
        return {"code": 0, "data": data.model_dump(mode="json"), "message": "ok"}
    except AnimationServiceError as error:
        _raise_service_error(error)


@router.get("/jobs/{job_id}/artifacts/{kind}")
async def read_animation_artifact(request: Request, job_id: str, kind: str):
    user_id = _user_id(request)
    if kind not in {"video", "thumbnail", "gif"}:
        raise HTTPException(404, detail={"code": "ANIMATION_ARTIFACT_NOT_FOUND", "message": "动画产物不存在"})
    try:
        async with get_db_session() as db:
            artifact, path = await get_owner_artifact(
                db, user_id=user_id, job_id=job_id, kind=kind  # type: ignore[arg-type]
            )
            try:
                byte_range = parse_byte_range(request.headers.get("range"), artifact.size_bytes)
            except AnimationServiceError as error:
                raise HTTPException(
                    416,
                    detail={"code": error.code, "message": error.message},
                    headers={"Content-Range": f"bytes */{artifact.size_bytes}"},
                ) from error
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": 'inline; filename="animation.mp4"',
            "X-Content-Type-Options": "nosniff",
        }
        if byte_range is None:
            start, end = 0, artifact.size_bytes - 1
            status_code = 200
        else:
            start, end = byte_range
            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{artifact.size_bytes}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            iter_file_range(path, start, end),
            status_code=status_code,
            media_type=artifact.mime_type,
            headers=headers,
        )
    except AnimationServiceError as error:
        _raise_service_error(error)
