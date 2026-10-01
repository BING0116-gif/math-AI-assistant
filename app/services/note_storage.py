"""Safe local development storage for immutable handwritten note revisions."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.config.settings import settings


class NoteStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredRevision:
    storage_key: str
    sha256: str
    size_bytes: int

ALLOWED_IMAGES = {
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".gif": ("image/gif", b"GIF87a"),
    ".webp": ("image/webp", b"RIFF"),
}


def storage_root() -> Path:
    return Path(settings.NOTE_STORAGE_ROOT).resolve()


def resolve_storage_key(storage_key: str) -> Path:
    key = PurePosixPath(storage_key)
    if not storage_key or key.is_absolute() or ".." in key.parts or "\\" in storage_key or ":" in storage_key:
        raise NoteStorageError("invalid note storage key")
    root = storage_root()
    candidate = (root / Path(*key.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise NoteStorageError("note storage path escapes root") from exc
    return candidate


def serialize_payload(payload: dict) -> bytes:
    try:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NoteStorageError("stroke payload must be JSON serializable") from exc
    if len(data) > settings.NOTE_MAX_REVISION_BYTES:
        raise NoteStorageError("stroke payload exceeds configured limit")
    return data


def publish_revision(*, note_id: str, page_id: str, revision_number: int, payload: dict) -> StoredRevision:
    data = serialize_payload(payload)
    storage_key = f"revisions/{note_id}/{page_id}/{revision_number}.json"
    target = resolve_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise NoteStorageError("unable to publish note revision") from exc
    return StoredRevision(storage_key=storage_key, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def read_revision(storage_key: str, expected_sha256: str, expected_size: int) -> dict:
    path = resolve_storage_key(storage_key)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise NoteStorageError("note revision file unavailable") from exc
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise NoteStorageError("note revision integrity check failed")
    try:
        value = json.loads(data)
    except json.JSONDecodeError as exc:
        raise NoteStorageError("note revision file is not valid JSON") from exc
    if not isinstance(value, dict):
        raise NoteStorageError("note revision payload must be an object")
    return value


def remove_revision(storage_key: str) -> None:
    try:
        resolve_storage_key(storage_key).unlink(missing_ok=True)
    except OSError:
        # The database transaction is already failing; an orphan is safer than
        # hiding the primary failure and is recoverable by the later sweeper.
        pass


def remove_storage_key(storage_key: str) -> None:
    """Best-effort cleanup used only by a committed SQL cleanup task."""
    try:
        resolve_storage_key(storage_key).unlink(missing_ok=True)
    except OSError as exc:
        raise NoteStorageError("unable to remove note storage object") from exc


def iter_storage_keys() -> set[str]:
    root = storage_root()
    if not root.exists(): return set()
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and not path.name.endswith(".tmp")}


def validate_image(filename: str, declared_type: str, data: bytes) -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower()
    expected = ALLOWED_IMAGES.get(suffix)
    if not expected or declared_type != expected[0]:
        raise NoteStorageError("unsupported image type")
    if not data or len(data) > settings.NOTE_MAX_ASSET_BYTES:
        raise NoteStorageError("image exceeds configured limit")
    if not data.startswith(expected[1]) or (suffix == ".webp" and data[8:12] != b"WEBP"):
        raise NoteStorageError("image signature does not match its type")
    return suffix, expected[0]


def publish_asset(*, note_id: str, page_id: str, filename: str, media_type: str, data: bytes) -> StoredRevision:
    suffix, _ = validate_image(filename, media_type, data)
    storage_key = f"assets/{note_id}/{page_id}/{uuid.uuid4().hex}{suffix}"
    target = resolve_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(data)
    except OSError as exc:
        raise NoteStorageError("unable to store note asset") from exc
    return StoredRevision(storage_key=storage_key, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def read_asset(storage_key: str, expected_sha256: str, expected_size: int) -> bytes:
    path = resolve_storage_key(storage_key)
    try: data = path.read_bytes()
    except OSError as exc: raise NoteStorageError("note asset unavailable") from exc
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise NoteStorageError("note asset integrity check failed")
    return data
