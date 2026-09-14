import subprocess
import uuid

from app.config.settings import settings
from app.services.animation_renderer import OneShotAnimationRunner
from ops.math_animator_poc.tracer.registry import TEMPLATES


def test_one_shot_runner_uses_fixed_hardened_command_and_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANIMATION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ANIMATION_RENDERER_IMAGE", "sha256:" + "e" * 64)
    job_id = str(uuid.uuid4())
    received = {}

    def executor(command, timeout):
        received["command"] = list(command)
        received["timeout"] = timeout
        definition = TEMPLATES["secant_to_tangent"]
        output = tmp_path / "quarantine" / job_id / definition.output_relative_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"0" * 180)
        return subprocess.CompletedProcess(command, 0, "", "")

    result = OneShotAnimationRunner(executor=executor).render_once(
        job_id=job_id, template_id="secant_to_tangent",
        expected_image_digest="sha256:" + "e" * 64,
        expected_source_sha256=TEMPLATES["secant_to_tangent"].source_sha256,
    )
    assert result.succeeded and result.artifact is not None
    command = received["command"]
    assert command[:3] == ["docker", "run", "--rm"]
    for required in ("none", "--read-only", "ALL", "no-new-privileges:true", "--pids-limit"):
        assert required in command
    assert "--network" in command
    assert result.artifact.storage_key == f"artifacts/{job_id}/video.mp4"


def test_runner_rejects_untrusted_inputs_before_executor(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ANIMATION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ANIMATION_RENDERER_IMAGE", "sha256:" + "e" * 64)

    def forbidden(*args):
        raise AssertionError("executor must not run")

    runner = OneShotAnimationRunner(executor=forbidden)
    common = {
        "expected_image_digest": "sha256:" + "e" * 64,
        "expected_source_sha256": "a" * 64,
    }
    assert runner.render_once(job_id="../escape", template_id="secant_to_tangent", **common).error_code == "JOB_ID_INVALID"
    assert runner.render_once(job_id=str(uuid.uuid4()), template_id="unknown", **common).error_code == "TEMPLATE_INVALID"
