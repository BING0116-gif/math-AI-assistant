"""Durable file-backed queue for the single-machine T15 tracer prototype.

This is intentionally separate from application data. It has no user model and
must not be reused as a production multi-user task store.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Iterator, Mapping

from .pipeline import LocalAnimationPipeline, PipelineResult


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FALLBACK = "fallback"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCEEDED, STATUS_FALLBACK, STATUS_FAILED, STATUS_CANCELLED}
)
MAX_REQUEST_BYTES = 512 * 1024
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_JOB_ID = re.compile(r"^anim-[a-f0-9]{32}$")


class LocalQueueError(ValueError):
    pass


class IdempotencyConflict(LocalQueueError):
    pass


@dataclass(frozen=True)
class LocalAnimationJob:
    job_id: str
    template_id: str
    request_sha256: str
    idempotency_key_sha256: str
    status: str
    worker_id: str | None
    claim_count: int
    recovery_count: int
    cancel_requested: bool
    created_at: str
    updated_at: str
    started_at: str | None = None
    heartbeat_at: str | None = None
    lease_expires_at: str | None = None
    completed_at: str | None = None
    pipeline_run_id: str | None = None
    pipeline_event_log: str | None = None
    output_path: str | None = None
    fallback: str | None = None
    error: str | None = None


class LocalFileTaskQueue:
    """Atomic short-lock operations over one directory per local job."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        lock_timeout_seconds: float = 2.0,
        stale_lock_seconds: float = 30.0,
    ) -> None:
        self.root = root.resolve()
        self.jobs_root = self.root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock_timeout_seconds = lock_timeout_seconds
        if stale_lock_seconds < 5.0:
            raise LocalQueueError("stale_lock_seconds must be at least 5")
        self.stale_lock_seconds = stale_lock_seconds

    def submit(
        self,
        raw_visual_spec: Mapping[str, Any],
        template_id: str,
        *,
        idempotency_key: str,
    ) -> LocalAnimationJob:
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise LocalQueueError("invalid idempotency_key")
        request = {"template_id": template_id, "visual_spec": dict(raw_visual_spec)}
        request_bytes = _canonical_json(request)
        if len(request_bytes) > MAX_REQUEST_BYTES:
            raise LocalQueueError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest().upper()
        request_hash = hashlib.sha256(request_bytes).hexdigest().upper()
        job_id = f"anim-{key_hash[:32].lower()}"
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=False, exist_ok=True)

        with self._lock(job_dir):
            state_path = job_dir / "job.json"
            if state_path.exists():
                existing = self._read_job(state_path)
                if existing.request_sha256 != request_hash:
                    raise IdempotencyConflict(
                        "idempotency key was already used with a different request"
                    )
                return existing

            now = self._iso_now()
            job = LocalAnimationJob(
                job_id=job_id,
                template_id=template_id,
                request_sha256=request_hash,
                idempotency_key_sha256=key_hash,
                status=STATUS_PENDING,
                worker_id=None,
                claim_count=0,
                recovery_count=0,
                cancel_requested=False,
                created_at=now,
                updated_at=now,
            )
            self._atomic_write(job_dir / "request.json", request_bytes)
            self._write_job(state_path, job)
            return job

    def get(self, job_id: str) -> LocalAnimationJob | None:
        job_dir = self._job_dir(job_id)
        state_path = job_dir / "job.json"
        if not state_path.is_file():
            return None
        with self._lock(job_dir):
            return self._read_job(state_path)

    def claim_next(self, worker_id: str, *, lease_seconds: float = 60.0) -> LocalAnimationJob | None:
        if not _WORKER_ID.fullmatch(worker_id):
            raise LocalQueueError("invalid worker_id")
        if lease_seconds < 5 or lease_seconds > 300:
            raise LocalQueueError("lease_seconds must be in [5, 300]")

        now = self.clock()
        for job_dir in sorted(self.jobs_root.glob("anim-*")):
            if not job_dir.is_dir() or not _JOB_ID.fullmatch(job_dir.name):
                continue
            try:
                with self._lock(job_dir):
                    job = self._read_job(job_dir / "job.json")
                    expired = job.status == STATUS_RUNNING and _parse_time(
                        job.lease_expires_at
                    ) <= now
                    if job.status != STATUS_PENDING and not expired:
                        continue
                    if job.cancel_requested:
                        cancelled = self._replace(
                            job,
                            status=STATUS_CANCELLED,
                            completed_at=_iso(now),
                            updated_at=_iso(now),
                            worker_id=None,
                            lease_expires_at=None,
                        )
                        self._write_job(job_dir / "job.json", cancelled)
                        continue
                    claimed = self._replace(
                        job,
                        status=STATUS_RUNNING,
                        worker_id=worker_id,
                        claim_count=job.claim_count + 1,
                        recovery_count=job.recovery_count + (1 if expired else 0),
                        started_at=job.started_at or _iso(now),
                        heartbeat_at=_iso(now),
                        lease_expires_at=_iso(now + timedelta(seconds=lease_seconds)),
                        updated_at=_iso(now),
                    )
                    self._write_job(job_dir / "job.json", claimed)
                    return claimed
            except FileNotFoundError:
                continue
        return None

    def heartbeat(self, job_id: str, worker_id: str, *, lease_seconds: float = 60.0) -> bool:
        if lease_seconds < 5 or lease_seconds > 300:
            raise LocalQueueError("lease_seconds must be in [5, 300]")
        job_dir = self._job_dir(job_id)
        with self._lock(job_dir):
            job = self._read_job(job_dir / "job.json")
            if job.status != STATUS_RUNNING or job.worker_id != worker_id:
                return False
            now = self.clock()
            updated = self._replace(
                job,
                heartbeat_at=_iso(now),
                lease_expires_at=_iso(now + timedelta(seconds=lease_seconds)),
                updated_at=_iso(now),
            )
            self._write_job(job_dir / "job.json", updated)
            return True

    def cancel(self, job_id: str) -> bool:
        job_dir = self._job_dir(job_id)
        with self._lock(job_dir):
            job = self._read_job(job_dir / "job.json")
            if job.status in TERMINAL_STATUSES:
                return job.status == STATUS_CANCELLED
            now = self._iso_now()
            if job.status == STATUS_PENDING:
                updated = self._replace(
                    job,
                    status=STATUS_CANCELLED,
                    cancel_requested=True,
                    completed_at=now,
                    updated_at=now,
                )
            else:
                updated = self._replace(job, cancel_requested=True, updated_at=now)
            self._write_job(job_dir / "job.json", updated)
            return True

    def is_cancel_requested(self, job_id: str) -> bool:
        job = self.get(job_id)
        return job is None or job.cancel_requested or job.status == STATUS_CANCELLED

    def load_request(self, job: LocalAnimationJob) -> dict[str, Any]:
        request_path = self._job_dir(job.job_id) / "request.json"
        raw = request_path.read_bytes()
        if hashlib.sha256(raw).hexdigest().upper() != job.request_sha256:
            raise LocalQueueError("persisted request hash mismatch")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise LocalQueueError("persisted request is invalid")
        return value

    def finish(
        self,
        job_id: str,
        worker_id: str,
        *,
        status: str,
        pipeline_result: PipelineResult | None = None,
        error: str | None = None,
    ) -> LocalAnimationJob:
        if status not in {STATUS_SUCCEEDED, STATUS_FALLBACK, STATUS_FAILED}:
            raise LocalQueueError("invalid terminal status")
        job_dir = self._job_dir(job_id)
        with self._lock(job_dir):
            job = self._read_job(job_dir / "job.json")
            if job.status != STATUS_RUNNING or job.worker_id != worker_id:
                raise LocalQueueError("job is not owned by this running worker")
            now = self._iso_now()
            if job.cancel_requested:
                status = STATUS_CANCELLED
            render = pipeline_result.render_result if pipeline_result else None
            updated = self._replace(
                job,
                status=status,
                worker_id=None,
                completed_at=now,
                lease_expires_at=None,
                updated_at=now,
                pipeline_run_id=pipeline_result.run_id if pipeline_result else None,
                pipeline_event_log=str(pipeline_result.event_log) if pipeline_result else None,
                output_path=str(render.output_path) if render and render.output_path else None,
                fallback=(pipeline_result.fallback if pipeline_result else None),
                error=_safe_error(error or (pipeline_result.error if pipeline_result else None)),
            )
            self._write_job(job_dir / "job.json", updated)
            return updated

    def _job_dir(self, job_id: str) -> Path:
        if not _JOB_ID.fullmatch(job_id):
            raise LocalQueueError("invalid job_id")
        return self.jobs_root / job_id

    @contextmanager
    def _lock(self, job_dir: Path) -> Iterator[None]:
        lock_dir = job_dir / ".lock"
        deadline = time.monotonic() + self.lock_timeout_seconds
        while True:
            try:
                lock_dir.mkdir()
                break
            except FileExistsError:
                try:
                    age = time.time() - lock_dir.stat().st_mtime
                    if age >= self.stale_lock_seconds:
                        lock_dir.rmdir()
                        continue
                except (FileNotFoundError, OSError):
                    pass
                if time.monotonic() >= deadline:
                    raise LocalQueueError(f"timed out acquiring local job lock: {job_dir.name}")
                time.sleep(0.01)
        try:
            yield
        finally:
            lock_dir.rmdir()

    def _iso_now(self) -> str:
        return _iso(self.clock())

    @staticmethod
    def _read_job(path: Path) -> LocalAnimationJob:
        return LocalAnimationJob(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write_job(path: Path, job: LocalAnimationJob) -> None:
        LocalFileTaskQueue._atomic_write(path, _canonical_json(asdict(job), pretty=True))

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_bytes(content)
        os.replace(temporary, path)

    @staticmethod
    def _replace(job: LocalAnimationJob, **changes: Any) -> LocalAnimationJob:
        value = asdict(job)
        value.update(changes)
        return LocalAnimationJob(**value)


class LocalQueueWorker:
    """Claim and execute one job with a cooperative heartbeat/cancel boundary."""

    def __init__(
        self,
        queue: LocalFileTaskQueue,
        pipeline: LocalAnimationPipeline,
        *,
        worker_id: str,
        lease_seconds: float = 60.0,
    ) -> None:
        self.queue = queue
        self.pipeline = pipeline
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def run_once(self) -> LocalAnimationJob | None:
        job = self.queue.claim_next(self.worker_id, lease_seconds=self.lease_seconds)
        if job is None:
            return None
        if self.queue.is_cancel_requested(job.job_id):
            return self.queue.finish(
                job.job_id,
                self.worker_id,
                status=STATUS_FAILED,
                error="cancelled before pipeline start",
            )

        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job.job_id, stop),
            daemon=True,
        )
        heartbeat.start()
        try:
            request = self.queue.load_request(job)
            result = self.pipeline.run_from_visual_spec(
                request["visual_spec"],
                request["template_id"],
            )
            terminal = STATUS_SUCCEEDED if result.status == "succeeded" else STATUS_FALLBACK
            return self.queue.finish(
                job.job_id,
                self.worker_id,
                status=terminal,
                pipeline_result=result,
            )
        except Exception as exc:
            return self.queue.finish(
                job.job_id,
                self.worker_id,
                status=STATUS_FAILED,
                error=str(exc),
            )
        finally:
            stop.set()
            heartbeat.join(timeout=1.0)

    def _heartbeat_loop(self, job_id: str, stop: threading.Event) -> None:
        interval = max(1.0, self.lease_seconds / 3.0)
        while not stop.wait(interval):
            try:
                if not self.queue.heartbeat(
                    job_id,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                ):
                    return
            except (OSError, LocalQueueError):
                return


def _canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise LocalQueueError("request must contain finite JSON values only") from exc
    return (text + ("\n" if pretty else "")).encode("utf-8")


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise LocalQueueError("clock must return timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _safe_error(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.replace("\x00", "").split())[:1000]
