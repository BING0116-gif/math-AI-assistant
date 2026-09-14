"""One-shot fixed-template Docker runner used only by the dedicated worker."""
from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from app.config.settings import settings
from app.services.animation_service import AnimationServiceError
from app.services.animation_storage import ValidatedArtifact, storage_root, validate_and_publish_video
from ops.math_animator_poc.tracer.models import MathAnimationSpec
from ops.math_animator_poc.tracer.registry import TEMPLATES, verify_trusted_source

Executor = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RenderAttemptResult:
    succeeded: bool
    error_code: str | None = None
    artifact: ValidatedArtifact | None = None


def _execute(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), capture_output=True, check=False, text=True,
        encoding="utf-8", errors="replace", shell=False, timeout=timeout,
    )


class OneShotAnimationRunner:
    """Execute exactly one reviewed scene in a constrained disposable container."""

    def __init__(self, *, executor: Executor = _execute) -> None:
        self.executor = executor

    def render_once(
        self,
        *,
        job_id: str,
        template_id: str,
        expected_image_digest: str,
        expected_source_sha256: str,
    ) -> RenderAttemptResult:
        try:
            if str(uuid.UUID(job_id)) != job_id.lower():
                raise ValueError
        except ValueError:
            return RenderAttemptResult(False, "JOB_ID_INVALID")
        image = settings.ANIMATION_RENDERER_IMAGE.strip().lower()
        if not image.startswith("sha256:") or len(image) != 71:
            return RenderAttemptResult(False, "RENDERER_IMAGE_INVALID")
        if image != expected_image_digest.lower():
            return RenderAttemptResult(False, "RENDERER_IMAGE_MISMATCH")
        definition = TEMPLATES.get(template_id)
        if definition is None:
            return RenderAttemptResult(False, "TEMPLATE_INVALID")
        try:
            source_hash = verify_trusted_source(definition).lower()
        except ValueError:
            return RenderAttemptResult(False, "TEMPLATE_INTEGRITY_FAILED")
        if source_hash != expected_source_sha256.lower():
            return RenderAttemptResult(False, "TEMPLATE_SOURCE_MISMATCH")

        quarantine = storage_root() / "quarantine" / job_id
        if quarantine.exists():
            shutil.rmtree(quarantine)
        quarantine.mkdir(parents=True, exist_ok=False)
        output = quarantine / definition.output_relative_path
        command = self._command(definition.source_path, definition.scene_name, quarantine, job_id, image)
        try:
            completed = self.executor(command, settings.ANIMATION_RENDER_TIMEOUT_SECONDS + 5)
            if completed.returncode != 0:
                return RenderAttemptResult(False, "RENDER_PROCESS_FAILED")
            artifact = validate_and_publish_video(job_id=job_id, quarantine_path=output)
            return RenderAttemptResult(True, artifact=artifact)
        except subprocess.TimeoutExpired:
            return RenderAttemptResult(False, "RENDER_TIMEOUT")
        except (OSError, AnimationServiceError):
            return RenderAttemptResult(False, "ARTIFACT_VALIDATION_FAILED")
        finally:
            shutil.rmtree(quarantine, ignore_errors=True)

    @staticmethod
    def _command(source: Path, scene: str, output: Path, job_id: str, image: str) -> list[str]:
        timeout = settings.ANIMATION_RENDER_TIMEOUT_SECONDS
        return [
            "docker", "run", "--rm", "--stop-timeout", "1",
            "--name", f"zhiwei-animation-{job_id[:12]}",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--cpus", "1",
            "--memory", "768m", "--pids-limit", "128",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
            "--mount", f"type=bind,src={source.resolve()},dst=/input/scene.py,readonly",
            "--mount", f"type=bind,src={output.resolve()},dst=/output",
            "--entrypoint", "/usr/bin/timeout", image, f"{max(1, timeout - 2)}s",
            "manim", "-ql", "--disable_caching", "--media_dir", "/output",
            "/input/scene.py", scene,
        ]
