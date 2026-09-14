from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.services.math_visualizer import mock_visual_spec

from ops.math_animator_poc.tracer.capability import (
    AnimationCapabilityError,
    LocalMathAnimationCapability,
)
from ops.math_animator_poc.tracer.local_queue import LocalFileTaskQueue


class LocalMathAnimationCapabilityTest(unittest.TestCase):
    def test_explicit_verified_request_is_queued_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            capability = LocalMathAnimationCapability(queue)
            result = capability.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                trigger="user_explicit",
                idempotency_key="explicit-1",
            )
            request = json.loads(
                (queue.jobs_root / result.job.job_id / "request.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.status, "queued")
        self.assertTrue(result.decision.admitted)
        self.assertEqual(request["admission"]["trigger"], "user_explicit")

    def test_low_strategy_score_uses_static_without_creating_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            result = LocalMathAnimationCapability(queue).submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                trigger="teaching_strategy",
                dynamic_process_score=0.79,
                idempotency_key="low-score",
            )
            jobs = list(queue.jobs_root.glob("anim-*"))

        self.assertEqual(result.status, "static_fallback")
        self.assertEqual(result.fallback, "t08_static")
        self.assertEqual(jobs, [])

    def test_high_strategy_score_is_queued_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            capability = LocalMathAnimationCapability(queue)
            first = capability.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                trigger="teaching_strategy",
                dynamic_process_score=0.9,
                idempotency_key="strategy-high",
            )
            second = capability.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                trigger="teaching_strategy",
                dynamic_process_score=0.9,
                idempotency_key="strategy-high",
            )

        self.assertEqual(first.job.job_id, second.job.job_id)
        self.assertEqual(first.decision.dynamic_process_score, 0.9)

    def test_no_trigger_and_semantic_mismatch_do_not_enqueue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            capability = LocalMathAnimationCapability(queue)
            no_trigger = capability.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                trigger="none",
                idempotency_key="none",
            )
            mismatch = capability.submit(
                mock_visual_spec("tangent_line"),
                "riemann_sum",
                trigger="user_explicit",
                idempotency_key="mismatch",
            )

        self.assertEqual(no_trigger.status, "static_fallback")
        self.assertEqual(mismatch.status, "static_fallback")
        self.assertIn("compatibility", mismatch.decision.reason)

    def test_taylor_and_invalid_scores_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capability = LocalMathAnimationCapability(LocalFileTaskQueue(Path(directory)))
            taylor = capability.submit(
                mock_visual_spec("tangent_line"),
                "taylor_approximation",
                trigger="user_explicit",
                idempotency_key="taylor",
            )
            self.assertEqual(taylor.status, "static_fallback")
            for value in (float("nan"), -0.1, 1.1, True):
                with self.subTest(value=value), self.assertRaises(AnimationCapabilityError):
                    capability.evaluate(
                        mock_visual_spec("tangent_line"),
                        "secant_to_tangent",
                        trigger="teaching_strategy",
                        dynamic_process_score=value,
                    )

    def test_strategy_trigger_requires_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capability = LocalMathAnimationCapability(LocalFileTaskQueue(Path(directory)))
            with self.assertRaises(AnimationCapabilityError):
                capability.evaluate(
                    mock_visual_spec("tangent_line"),
                    "secant_to_tangent",
                    trigger="teaching_strategy",
                )


if __name__ == "__main__":
    unittest.main()
