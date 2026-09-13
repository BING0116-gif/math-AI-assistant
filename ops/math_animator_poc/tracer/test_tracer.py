from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.math_animator_poc.tracer.models import MathAnimationSpec, SpecValidationError
from ops.math_animator_poc.tracer.registry import resolve_template
from ops.math_animator_poc.tracer.runner import LocalTracerRunner


def _spec(template_id: str = "secant_to_tangent") -> MathAnimationSpec:
    return MathAnimationSpec.from_mapping(
        {"schema_version": 1, "template_id": template_id, "parameters": {}}
    )


def _write_fake_mp4(command: list[str]) -> None:
    output_mount = next(
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--mount" and command[index + 1].endswith("dst=/output")
    )
    output_root = Path(output_mount.removeprefix("type=bind,src=").removesuffix(",dst=/output"))
    scene = command[-1]
    relative = Path("videos/scene/480p15") / f"{scene}.mp4"
    target = output_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 256)


class MathAnimationSpecTest(unittest.TestCase):
    def test_canonical_form_is_stable(self) -> None:
        first = MathAnimationSpec.from_json_bytes(
            b'{"template_id":"secant_to_tangent","parameters":{},"schema_version":1}'
        )
        second = _spec()
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())

    def test_rejects_unknown_fields_and_non_finite_values(self) -> None:
        with self.assertRaises(SpecValidationError):
            MathAnimationSpec.from_mapping(
                {
                    "schema_version": 1,
                    "template_id": "secant_to_tangent",
                    "parameters": {},
                    "python": "import os",
                }
            )
        with self.assertRaises(SpecValidationError):
            MathAnimationSpec.from_json_bytes(
                b'{"schema_version":1,"schema_version":1,'
                b'"template_id":"secant_to_tangent","parameters":{}}'
            )
        with self.assertRaises(SpecValidationError):
            MathAnimationSpec.from_mapping(
                {
                    "schema_version": 1,
                    "template_id": "secant_to_tangent",
                    "parameters": {"x": float("nan")},
                }
            )

    def test_registry_rejects_paths_code_and_unknown_parameters(self) -> None:
        for template_id in ("../../evil.py", "os.system('id')", "unknown"):
            with self.subTest(template_id=template_id), self.assertRaises(SpecValidationError):
                resolve_template(_spec(template_id))
        with self.assertRaises(SpecValidationError):
            resolve_template(
                MathAnimationSpec.from_mapping(
                    {
                        "schema_version": 1,
                        "template_id": "secant_to_tangent",
                        "parameters": {"source": "import requests"},
                    }
                )
            )


class LocalTracerRunnerTest(unittest.TestCase):
    def test_command_enforces_isolation_and_success_is_cached(self) -> None:
        calls: list[list[str]] = []

        def executor(command, timeout):
            materialized = list(command)
            calls.append(materialized)
            _write_fake_mp4(materialized)
            return subprocess.CompletedProcess(materialized, 0, "ok", "")

        with tempfile.TemporaryDirectory() as directory:
            runner = LocalTracerRunner(Path(directory), executor=executor)
            first = runner.render(_spec())
            second = runner.render(_spec())

        self.assertEqual(first.status, "succeeded")
        self.assertEqual(first.attempts, 1)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.attempts, 0)
        self.assertEqual(len(calls), 1)
        command = calls[0]
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("no-new-privileges:true", command)
        self.assertIn("/usr/bin/timeout", command)
        self.assertIn("28s", command)
        input_mount = next(
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount" and command[index + 1].endswith("dst=/input/scene.py,readonly")
        )
        self.assertTrue(input_mount.endswith("secant_to_tangent.py,dst=/input/scene.py,readonly"))
        self.assertNotIn("/var/run/docker.sock", " ".join(command))

    def test_failure_retries_once_then_returns_static_fallback(self) -> None:
        calls = 0

        def executor(command, timeout):
            nonlocal calls
            calls += 1
            return subprocess.CompletedProcess(list(command), 1, "", "controlled failure")

        with tempfile.TemporaryDirectory() as directory:
            result = LocalTracerRunner(Path(directory), executor=executor).render(_spec())
            metadata = json.loads(
                (Path(directory) / result.cache_key / "job.json").read_text(encoding="utf-8")
            )

        self.assertEqual(calls, 2)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.fallback, "t08_static")
        self.assertEqual(metadata["fallback"], "t08_static")

    def test_transient_failure_succeeds_on_second_attempt(self) -> None:
        calls = 0

        def executor(command, timeout):
            nonlocal calls
            calls += 1
            materialized = list(command)
            if calls == 2:
                _write_fake_mp4(materialized)
                return subprocess.CompletedProcess(materialized, 0, "ok", "")
            return subprocess.CompletedProcess(materialized, 1, "", "transient")

        with tempfile.TemporaryDirectory() as directory:
            result = LocalTracerRunner(Path(directory), executor=executor).render(_spec())

        self.assertEqual(calls, 2)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.attempts, 2)


if __name__ == "__main__":
    unittest.main()
