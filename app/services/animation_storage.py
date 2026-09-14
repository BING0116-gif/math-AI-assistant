"""Validated, owner-scoped animation artifact storage and HTTP ranges."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.data.models import AnimationArtifact, AnimationJob
from app.services.animation_service import AnimationServiceError

ArtifactKind = Literal["video", "thumbnail", "gif"]
_KINDS = {"video": ("video/mp4", ".mp4")}
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


@dataclass(frozen=True)
class ValidatedArtifact:
    storage_key: str
    mime_type: str
    sha256: str
    size_bytes: int


def storage_root() -> Path:
    return Path(settings.ANIMATION_STORAGE_ROOT).resolve()


def resolve_storage_key(storage_key: str) -> Path:
    key = PurePosixPath(storage_key)
    if (
        not storage_key
        or key.is_absolute()
        or ".." in key.parts
        or "\\" in storage_key
        or ":" in storage_key
    ):
        raise AnimationServiceError("ANIMATION_ARTIFACT_NOT_FOUND", "动画产物不存在")
    root = storage_root()
    candidate = (root / Path(*key.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AnimationServiceError("ANIMATION_ARTIFACT_NOT_FOUND", "动画产物不存在") from exc
    return candidate


def validate_and_publish_video(*, job_id: str, quarantine_path: Path) -> ValidatedArtifact:
    root = storage_root()
    quarantine_root = (root / "quarantine").resolve()
    source = quarantine_path.resolve()
    try:
        source.relative_to(quarantine_root)
    except ValueError as exc:
        raise AnimationServiceError("ARTIFACT_QUARANTINE_INVALID", "动画产物不在隔离区") from exc
    if not source.is_file() or source.is_symlink():
        raise AnimationServiceError("ARTIFACT_INVALID", "动画产物缺失或类型无效")
    size = source.stat().st_size
    if size < 128 or size > settings.ANIMATION_MAX_OUTPUT_BYTES:
        raise AnimationServiceError("ARTIFACT_INVALID", "动画产物大小无效")
    with source.open("rb") as stream:
        header = stream.read(32)
        if b"ftyp" not in header:
            raise AnimationServiceError("ARTIFACT_INVALID", "动画产物不是有效 MP4")
        digest = hashlib.sha256()
        digest.update(header)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    storage_key = f"artifacts/{job_id}/video.mp4"
    target = resolve_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return ValidatedArtifact(storage_key, "video/mp4", digest.hexdigest(), size)


async def get_owner_artifact(
    db: AsyncSession,
    *,
    user_id: str,
    job_id: str,
    kind: ArtifactKind,
) -> tuple[AnimationArtifact, Path]:
    artifact = await db.scalar(
        select(AnimationArtifact)
        .join(AnimationJob, AnimationJob.id == AnimationArtifact.job_id)
        .where(
            AnimationArtifact.job_id == job_id,
            AnimationArtifact.user_id == user_id,
            AnimationArtifact.kind == kind,
            AnimationArtifact.validation_status == "validated",
            AnimationArtifact.published_at.is_not(None),
            AnimationJob.status == "succeeded",
            AnimationJob.user_id == user_id,
        )
    )
    if artifact is None:
        raise AnimationServiceError("ANIMATION_ARTIFACT_NOT_FOUND", "动画产物不存在")
    path = resolve_storage_key(artifact.storage_key)
    if not path.is_file() or path.is_symlink() or path.stat().st_size != artifact.size_bytes:
        raise AnimationServiceError("ANIMATION_ARTIFACT_NOT_FOUND", "动画产物不存在")
    return artifact, path


def parse_byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    match = _RANGE.fullmatch(value.strip())
    if not match or "," in value:
        raise AnimationServiceError("RANGE_NOT_SATISFIABLE", "媒体范围请求无效")
    first, last = match.groups()
    if not first and not last:
        raise AnimationServiceError("RANGE_NOT_SATISFIABLE", "媒体范围请求无效")
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
        if start >= size or end < start:
            raise AnimationServiceError("RANGE_NOT_SATISFIABLE", "媒体范围请求无效")
    else:
        suffix = int(last)
        if suffix <= 0:
            raise AnimationServiceError("RANGE_NOT_SATISFIABLE", "媒体范围请求无效")
        start = max(0, size - suffix)
        end = size - 1
    return start, end


def iter_file_range(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining:
            chunk = stream.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
