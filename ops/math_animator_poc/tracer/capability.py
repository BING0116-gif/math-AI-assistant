"""Deterministic local admission gate for MathAnimationCapability."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .local_queue import LocalAnimationJob, LocalFileTaskQueue
from .visual_adapter import VisualAdapterError, adapt_math_visual_spec


TRIGGER_USER_EXPLICIT = "user_explicit"
TRIGGER_TEACHING_STRATEGY = "teaching_strategy"
TRIGGER_NONE = "none"
ALLOWED_TRIGGERS = frozenset(
    {TRIGGER_USER_EXPLICIT, TRIGGER_TEACHING_STRATEGY, TRIGGER_NONE}
)
MIN_DYNAMIC_PROCESS_SCORE = 0.8


class AnimationCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class AnimationAdmissionDecision:
    admitted: bool
    trigger: str
    requested_template_id: str
    reason: str
    dynamic_process_score: float | None


@dataclass(frozen=True)
class AnimationCapabilitySubmission:
    status: str
    decision: AnimationAdmissionDecision
    job: LocalAnimationJob | None
    fallback: str | None = None


class LocalMathAnimationCapability:
    """Admit only explicit or high-value dynamic requests to the local queue."""

    def __init__(
        self,
        queue: LocalFileTaskQueue,
        *,
        dynamic_score_threshold: float = MIN_DYNAMIC_PROCESS_SCORE,
    ) -> None:
        if not math.isfinite(dynamic_score_threshold) or not 0 <= dynamic_score_threshold <= 1:
            raise AnimationCapabilityError("dynamic score threshold must be finite in [0,1]")
        self.queue = queue
        self.dynamic_score_threshold = dynamic_score_threshold

    def evaluate(
        self,
        raw_visual_spec: Mapping[str, Any],
        requested_template_id: str,
        *,
        trigger: str,
        dynamic_process_score: float | None = None,
    ) -> AnimationAdmissionDecision:
        if trigger not in ALLOWED_TRIGGERS:
            raise AnimationCapabilityError(f"unsupported animation trigger: {trigger!r}")
        score = _validate_score(dynamic_process_score)

        if trigger == TRIGGER_NONE:
            return AnimationAdmissionDecision(
                False,
                trigger,
                requested_template_id,
                "animation was not explicitly requested and no teaching strategy selected it",
                score,
            )
        if trigger == TRIGGER_TEACHING_STRATEGY:
            if score is None:
                raise AnimationCapabilityError(
                    "teaching_strategy trigger requires dynamic_process_score"
                )
            if score < self.dynamic_score_threshold:
                return AnimationAdmissionDecision(
                    False,
                    trigger,
                    requested_template_id,
                    "dynamic process score is below the local animation threshold",
                    score,
                )

        try:
            adapt_math_visual_spec(raw_visual_spec, requested_template_id)
        except VisualAdapterError as exc:
            return AnimationAdmissionDecision(
                False,
                trigger,
                requested_template_id,
                f"T08 compatibility check rejected the animation: {exc}",
                score,
            )

        reason = (
            "user explicitly requested an animation"
            if trigger == TRIGGER_USER_EXPLICIT
            else "teaching strategy rated the dynamic process above threshold"
        )
        return AnimationAdmissionDecision(
            True,
            trigger,
            requested_template_id,
            reason,
            score,
        )

    def submit(
        self,
        raw_visual_spec: Mapping[str, Any],
        requested_template_id: str,
        *,
        trigger: str,
        idempotency_key: str,
        dynamic_process_score: float | None = None,
    ) -> AnimationCapabilitySubmission:
        decision = self.evaluate(
            raw_visual_spec,
            requested_template_id,
            trigger=trigger,
            dynamic_process_score=dynamic_process_score,
        )
        if not decision.admitted:
            return AnimationCapabilitySubmission(
                status="static_fallback",
                decision=decision,
                job=None,
                fallback="t08_static",
            )

        job = self.queue.submit(
            raw_visual_spec,
            requested_template_id,
            idempotency_key=idempotency_key,
            admission={
                "dynamic_process_score": decision.dynamic_process_score,
                "reason": decision.reason,
                "trigger": decision.trigger,
            },
        )
        return AnimationCapabilitySubmission(
            status="queued",
            decision=decision,
            job=job,
        )


def _validate_score(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise AnimationCapabilityError("dynamic_process_score must be numeric")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise AnimationCapabilityError("dynamic_process_score must be numeric") from exc
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise AnimationCapabilityError("dynamic_process_score must be finite in [0,1]")
    return score
