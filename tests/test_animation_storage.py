from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import AnimationArtifact, AnimationJob, Base, User
from app.services.animation_service import AnimationServiceError
from app.services.animation_storage import (
    get_owner_artifact,
    iter_file_range,
    parse_byte_range,
    resolve_storage_key,
    validate_and_publish_video,
)


def _mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom" + b"0" * 180


def test_quarantine_validation_publication_and_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANIMATION_STORAGE_ROOT", str(tmp_path))
    source = tmp_path / "quarantine" / "job" / "video.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(_mp4())
    result = validate_and_publish_video(job_id="job", quarantine_path=source)
    target = resolve_storage_key(result.storage_key)
    assert target.read_bytes() == _mp4()
    assert parse_byte_range(None, result.size_bytes) is None
    assert parse_byte_range("bytes=0-9", result.size_bytes) == (0, 9)
    assert parse_byte_range("bytes=-10", result.size_bytes) == (result.size_bytes - 10, result.size_bytes - 1)
    assert b"".join(iter_file_range(target, 2, 11)) == _mp4()[2:12]


@pytest.mark.parametrize("key", ["../x.mp4", "/x.mp4", "C:/x.mp4", "\\\\host\\x.mp4"])
def test_storage_key_escape_is_rejected(tmp_path, monkeypatch, key):
    monkeypatch.setattr(settings, "ANIMATION_STORAGE_ROOT", str(tmp_path))
    with pytest.raises(AnimationServiceError):
        resolve_storage_key(key)


@pytest.mark.parametrize("value", ["bytes=", "bytes=9-2", "bytes=999-", "items=0-1", "bytes=0-1,3-4"])
def test_invalid_ranges_are_rejected(value):
    with pytest.raises(AnimationServiceError) as exc:
        parse_byte_range(value, 100)
    assert exc.value.code == "RANGE_NOT_SATISFIABLE"


@pytest.mark.asyncio
async def test_artifact_lookup_hides_foreign_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANIMATION_STORAGE_ROOT", str(tmp_path))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(timezone.utc)
    path = tmp_path / "artifacts" / "job-1" / "video.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(_mp4())
    async with factory() as db:
        db.add_all([
            User(id="owner-a", username="storage-a", email="storage-a@example.test", password_hash="x"),
            User(id="owner-b", username="storage-b", email="storage-b@example.test", password_hash="x"),
        ])
        db.add(AnimationJob(
            id="job-1", user_id="owner-a", idempotency_key="storage-job-01",
            request_fingerprint="a" * 64, template_id="secant_to_tangent",
            template_source_sha256="b" * 64, renderer_image_digest="sha256:" + "c" * 64,
            trigger="user_explicit", admission_snapshot={}, visual_spec_snapshot={"type": "tangent_line"},
            status="succeeded", stage="completed", attempt_count=1, created_at=now, updated_at=now,
        ))
        db.add(AnimationArtifact(
            id="artifact-1", job_id="job-1", user_id="owner-a", kind="video",
            storage_key="artifacts/job-1/video.mp4", mime_type="video/mp4",
            sha256="d" * 64, size_bytes=len(_mp4()), validation_status="validated", published_at=now,
        ))
        await db.flush()
        artifact, resolved = await get_owner_artifact(db, user_id="owner-a", job_id="job-1", kind="video")
        assert artifact.id == "artifact-1" and resolved == path.resolve()
        with pytest.raises(AnimationServiceError) as hidden:
            await get_owner_artifact(db, user_id="owner-b", job_id="job-1", kind="video")
        assert hidden.value.code == "ANIMATION_ARTIFACT_NOT_FOUND"
    await engine.dispose()
