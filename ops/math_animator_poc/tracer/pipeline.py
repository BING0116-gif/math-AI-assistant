"""Observable local pipeline joining T08 validation to the trusted renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .models import MathAnimationSpec
from .runner import LocalTracerRunner, RenderResult
from .visual_adapter import VisualAdapterError, adapt_math_visual_spec


@dataclass(frozen=True)
class PipelineEvent:
    sequence: int
    stage: str
    status: str
    timestamp: str
    details: Mapping[str, object]


@dataclass(frozen=True)
class PipelineResult:
    status: str
    run_id: str
    event_log: Path
    animation_spec: MathAnimationSpec | None
    render_result: RenderResult | None
    fallback: str | None = None
    error: str | None = None


class LocalAnimationPipeline:
    """Run and persist a safe event timeline without creating production state."""

    def __init__(self, output_root: Path, *, runner: LocalTracerRunner | None = None) -> None:
        self.output_root = output_root.resolve()
        self.runner = runner or LocalTracerRunner(self.output_root / "cache")

    def run_from_visual_spec(
        self,
        raw_visual_spec: Mapping[str, Any],
        requested_template_id: str,
    ) -> PipelineResult:
        run_id = uuid4().hex
        event_log = self.output_root / "events" / f"{run_id}.jsonl"
        events: list[PipelineEvent] = []

        def record(stage: str, status: str, details: Mapping[str, object] | None = None) -> None:
            event = PipelineEvent(
                sequence=len(events) + 1,
                stage=stage,
                status=status,
                timestamp=datetime.now(timezone.utc).isoformat(),
                details=dict(details or {}),
            )
            events.append(event)
            event_log.parent.mkdir(parents=True, exist_ok=True)
            with event_log.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")

        record("concept_analysis", "accepted", {"requested_template_id": requested_template_id})
        record("visual_design", "received", {"source": "t08_math_visual_spec"})
        try:
            animation_spec = adapt_math_visual_spec(raw_visual_spec, requested_template_id)
        except VisualAdapterError as exc:
            record("math_animation_spec", "rejected", {"error": str(exc)})
            record("fallback", "selected", {"fallback": "t08_static"})
            return PipelineResult(
                status="fallback",
                run_id=run_id,
                event_log=event_log,
                animation_spec=None,
                render_result=None,
                fallback="t08_static",
                error=str(exc),
            )

        record(
            "math_animation_spec",
            "validated",
            {"template_id": animation_spec.template_id, "schema_version": 1},
        )
        record("trusted_template_selection", "accepted", {"template_id": animation_spec.template_id})

        def render_event(event_type: str, details: Mapping[str, object]) -> None:
            statuses = {
                "cache_hit": "hit",
                "fallback_selected": "selected",
                "render_attempt_failed": "failed",
                "render_attempt_started": "started",
                "render_succeeded": "succeeded",
            }
            status = statuses.get(event_type, "observed")
            record(event_type, status, details)

        render_result = self.runner.render(animation_spec, event_sink=render_event)
        if render_result.status == "succeeded":
            record(
                "pipeline",
                "succeeded",
                {"cache_hit": render_result.cache_hit, "cache_key": render_result.cache_key},
            )
            return PipelineResult(
                status="succeeded",
                run_id=run_id,
                event_log=event_log,
                animation_spec=animation_spec,
                render_result=render_result,
            )

        record("pipeline", "fallback", {"fallback": render_result.fallback or "t08_static"})
        return PipelineResult(
            status="fallback",
            run_id=run_id,
            event_log=event_log,
            animation_spec=animation_spec,
            render_result=render_result,
            fallback=render_result.fallback or "t08_static",
            error=render_result.error,
        )
