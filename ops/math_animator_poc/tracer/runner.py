"""Local Docker runner for fixed, hash-pinned Manim templates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Callable, Mapping, Sequence

from .models import MathAnimationSpec
from .registry import TemplateDefinition, resolve_template, verify_trusted_source


RENDERER_IMAGE = "sha256:e0c8c2909a56756b6ef8ea05138cfa1cea1fea6db5d176e8ff58715959532635"
MAX_RENDER_ATTEMPTS = 2
MAX_MEDIA_BYTES = 20 * 1024 * 1024

CommandExecutor = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]
RenderEventSink = Callable[[str, Mapping[str, object]], None]


@dataclass(frozen=True)
class RenderResult:
    status: str
    cache_key: str
    output_path: Path | None
    attempts: int
    cache_hit: bool
    fallback: str | None = None
    error: str | None = None


def _default_executor(command: Sequence[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=timeout_seconds,
    )


class LocalTracerRunner:
    """Render a validated spec without exposing source paths or Docker arguments."""

    def __init__(
        self,
        output_root: Path,
        *,
        executor: CommandExecutor = _default_executor,
        timeout_seconds: float = 30.0,
        renderer_image: str = RENDERER_IMAGE,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be in (0, 120]")
        if renderer_image != RENDERER_IMAGE:
            raise ValueError("renderer image must match the reviewed digest")
        self.output_root = output_root.resolve()
        self.executor = executor
        self.timeout_seconds = timeout_seconds
        self.renderer_image = renderer_image

    def render(
        self,
        spec: MathAnimationSpec,
        *,
        event_sink: RenderEventSink | None = None,
    ) -> RenderResult:
        definition = resolve_template(spec)
        source_hash = verify_trusted_source(definition)
        cache_key = self._cache_key(spec, definition)
        job_dir = self.output_root / cache_key
        output_path = job_dir / definition.output_relative_path
        metadata_path = job_dir / "job.json"
        job_dir.mkdir(parents=True, exist_ok=True)

        cached = self._load_valid_cache(metadata_path, output_path, cache_key)
        if cached:
            self._emit(event_sink, "cache_hit", {"cache_key": cache_key})
            return RenderResult("succeeded", cache_key, output_path, 0, True)

        errors: list[str] = []
        started = time.monotonic()
        for attempt in range(1, MAX_RENDER_ATTEMPTS + 1):
            self._emit(event_sink, "render_attempt_started", {"attempt": attempt})
            command = self._build_command(definition, job_dir, cache_key)
            try:
                completed = self.executor(command, self.timeout_seconds + 5.0)
                if completed.returncode == 0:
                    media_hash = self._validate_media(output_path)
                    self._write_metadata(
                        metadata_path,
                        {
                            "attempts": attempt,
                            "cache_key": cache_key,
                            "duration_seconds": round(time.monotonic() - started, 3),
                            "media_sha256": media_hash,
                            "renderer_image": self.renderer_image,
                            "schema_version": spec.schema_version,
                            "source_sha256": source_hash,
                            "status": "succeeded",
                            "template_id": spec.template_id,
                        },
                    )
                    self._emit(
                        event_sink,
                        "render_succeeded",
                        {"attempt": attempt, "media_sha256": media_hash},
                    )
                    return RenderResult("succeeded", cache_key, output_path, attempt, False)
                error = self._safe_error(completed.stderr or completed.stdout)
                errors.append(error)
                self._emit(
                    event_sink,
                    "render_attempt_failed",
                    {"attempt": attempt, "error": error},
                )
            except subprocess.TimeoutExpired:
                error = f"render attempt {attempt} timed out"
                errors.append(error)
                self._emit(
                    event_sink,
                    "render_attempt_failed",
                    {"attempt": attempt, "error": error},
                )
            except (OSError, ValueError) as exc:
                error = self._safe_error(str(exc))
                errors.append(error)
                self._emit(
                    event_sink,
                    "render_attempt_failed",
                    {"attempt": attempt, "error": error},
                )

        error = errors[-1] if errors else "render failed without diagnostic output"
        self._write_metadata(
            metadata_path,
            {
                "attempts": MAX_RENDER_ATTEMPTS,
                "cache_key": cache_key,
                "error": error,
                "fallback": "t08_static",
                "renderer_image": self.renderer_image,
                "schema_version": spec.schema_version,
                "source_sha256": source_hash,
                "status": "failed",
                "template_id": spec.template_id,
            },
        )
        self._emit(
            event_sink,
            "fallback_selected",
            {"fallback": "t08_static", "reason": error},
        )
        return RenderResult(
            "failed",
            cache_key,
            None,
            MAX_RENDER_ATTEMPTS,
            False,
            fallback="t08_static",
            error=error,
        )

    @staticmethod
    def _emit(
        sink: RenderEventSink | None,
        event_type: str,
        details: Mapping[str, object],
    ) -> None:
        if sink is not None:
            sink(event_type, details)

    def _cache_key(self, spec: MathAnimationSpec, definition: TemplateDefinition) -> str:
        digest = hashlib.sha256()
        digest.update(spec.canonical_bytes())
        digest.update(b"\0")
        digest.update(self.renderer_image.encode("ascii"))
        digest.update(b"\0")
        digest.update(definition.source_sha256.encode("ascii"))
        return digest.hexdigest()

    def _build_command(
        self,
        definition: TemplateDefinition,
        job_dir: Path,
        cache_key: str,
    ) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--stop-timeout",
            "1",
            "--name",
            f"zhiwei-t15-{cache_key[:16]}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--cpus",
            "1",
            "--memory",
            "768m",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "--mount",
            f"type=bind,src={definition.source_path.resolve()},dst=/input/scene.py,readonly",
            "--mount",
            f"type=bind,src={job_dir.resolve()},dst=/output",
            "--entrypoint",
            "/usr/bin/timeout",
            self.renderer_image,
            f"{max(1.0, self.timeout_seconds - 2.0):g}s",
            "manim",
            "-ql",
            "--disable_caching",
            "--media_dir",
            "/output",
            "/input/scene.py",
            definition.scene_name,
        ]

    @staticmethod
    def _validate_media(output_path: Path) -> str:
        if not output_path.is_file():
            raise ValueError("renderer exited successfully but expected media is missing")
        size = output_path.stat().st_size
        if size < 128 or size > MAX_MEDIA_BYTES:
            raise ValueError(f"media size outside allowed range: {size}")
        header = output_path.read_bytes()[:32]
        if b"ftyp" not in header:
            raise ValueError("media is not an MP4 container")
        return hashlib.sha256(output_path.read_bytes()).hexdigest().upper()

    @staticmethod
    def _safe_error(value: str) -> str:
        return " ".join(value.replace("\x00", "").split())[:1000] or "render failed"

    @staticmethod
    def _write_metadata(path: Path, value: dict[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    @classmethod
    def _load_valid_cache(
        cls,
        metadata_path: Path,
        output_path: Path,
        cache_key: str,
    ) -> bool:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("status") != "succeeded" or metadata.get("cache_key") != cache_key:
                return False
            return cls._validate_media(output_path) == metadata.get("media_sha256")
        except (OSError, ValueError, json.JSONDecodeError):
            return False
