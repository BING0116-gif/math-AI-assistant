from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.services.math_visualizer import mock_visual_spec

from ops.math_animator_poc.tracer.models import MathAnimationSpec
from ops.math_animator_poc.tracer.pipeline import LocalAnimationPipeline
from ops.math_animator_poc.tracer.runner import RenderResult
from ops.math_animator_poc.tracer.visual_adapter import (
    VisualAdapterError,
    adapt_math_visual_spec,
)


def _area_visual_spec() -> dict:
    return {
        "type": "area_under_curve",
        "title": "y=x^2 on [0,2]",
        "viewport": {"x_min": 0, "x_max": 2, "y_min": 0, "y_max": 4},
        "series": [
            {"kind": "curve", "label": "y=x^2", "points": [[0, 0], [1, 1], [2, 4]]},
            {
                "kind": "area",
                "label": "area",
                "points": [[0, 0], [1, 1], [2, 4], [2, 0], [0, 0]],
            },
        ],
        "annotations": [],
        "teaching_note": "Riemann sums approximate the verified area.",
        "verification_request": {
            "type": "integral",
            "expression": "x**2",
            "variable": "x",
            "lower": 0,
            "upper": 2,
            "claimed": 8 / 3,
        },
    }


class VisualAdapterTest(unittest.TestCase):
    def test_verified_tangent_maps_to_secant_template(self) -> None:
        result = adapt_math_visual_spec(
            mock_visual_spec("tangent_line"),
            "secant_to_tangent",
        )
        self.assertEqual(result.template_id, "secant_to_tangent")
        self.assertEqual(result.parameters, {})

    def test_verified_area_maps_to_riemann_template(self) -> None:
        result = adapt_math_visual_spec(_area_visual_spec(), "riemann_sum")
        self.assertEqual(result.template_id, "riemann_sum")

    def test_mismatched_or_unverified_semantics_are_rejected(self) -> None:
        with self.assertRaises(VisualAdapterError):
            adapt_math_visual_spec(mock_visual_spec("tangent_line"), "riemann_sum")
        with self.assertRaises(VisualAdapterError, msg="Taylor must wait for a verified T08 contract"):
            adapt_math_visual_spec(mock_visual_spec("tangent_line"), "taylor_approximation")


class FakeRunner:
    def __init__(self, result: RenderResult) -> None:
        self.result = result
        self.received: MathAnimationSpec | None = None

    def render(self, spec: MathAnimationSpec, *, event_sink=None) -> RenderResult:
        self.received = spec
        if event_sink:
            event_sink("render_attempt_started", {"attempt": 1})
            event_sink("render_succeeded", {"attempt": 1, "media_sha256": "A" * 64})
        return self.result


class LocalAnimationPipelineTest(unittest.TestCase):
    def test_success_persists_ordered_observable_events(self) -> None:
        render_result = RenderResult(
            status="succeeded",
            cache_key="cache-key",
            output_path=Path("animation.mp4"),
            attempts=1,
            cache_hit=False,
        )
        fake = FakeRunner(render_result)
        with tempfile.TemporaryDirectory() as directory:
            result = LocalAnimationPipeline(Path(directory), runner=fake).run_from_visual_spec(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
            )
            events = [json.loads(line) for line in result.event_log.read_text().splitlines()]

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(fake.received.template_id, "secant_to_tangent")
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(
            [event["stage"] for event in events],
            [
                "concept_analysis",
                "visual_design",
                "math_animation_spec",
                "trusted_template_selection",
                "render_attempt_started",
                "render_succeeded",
                "pipeline",
            ],
        )
        self.assertEqual(events[4]["status"], "started")
        self.assertEqual(events[5]["status"], "succeeded")

    def test_adapter_rejection_falls_back_without_starting_runner(self) -> None:
        fake = FakeRunner(
            RenderResult("succeeded", "unused", Path("unused"), 1, False)
        )
        with tempfile.TemporaryDirectory() as directory:
            result = LocalAnimationPipeline(Path(directory), runner=fake).run_from_visual_spec(
                mock_visual_spec("function_plot"),
                "secant_to_tangent",
            )
            events = [json.loads(line) for line in result.event_log.read_text().splitlines()]

        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.fallback, "t08_static")
        self.assertIsNone(fake.received)
        self.assertEqual(events[-1]["stage"], "fallback")


if __name__ == "__main__":
    unittest.main()
