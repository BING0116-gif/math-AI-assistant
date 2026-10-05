"""Versioned quality-gate configuration and deterministic evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _GateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockingGates(_GateModel):
    safety_pass_rate: float = Field(ge=0, le=1)
    category_regression_max_pp: float = Field(ge=0, le=100)
    hallucination_rate_max: float = Field(ge=0, le=1)


class ObservatoryGates(_GateModel):
    final_correctness_target: float = Field(ge=0, le=1)
    key_steps_hit_target: float = Field(ge=0, le=1)
    complete_answer_target: float = Field(ge=0, le=1)


class QualityGates(_GateModel):
    schema_version: str = Field(pattern=r"^1\.0$")
    blocking: BlockingGates
    observatory: ObservatoryGates

    @model_validator(mode="after")
    def blocking_thresholds_are_stricter_than_targets(self) -> "QualityGates":
        if self.blocking.safety_pass_rate != 1.0:
            raise ValueError("safety_pass_rate must keep the 100% safety policy")
        return self


def load_gates(path: str | Path) -> QualityGates:
    gate_path = Path(path)
    if not gate_path.is_file():
        raise ValueError(f"missing gates configuration: {gate_path}")
    try:
        payload = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid gates YAML: {gate_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("gates configuration must be a mapping")
    return QualityGates.model_validate(payload)


def _summary_metric(summary: dict[str, Any], name: str) -> float | None:
    value = summary.get(name)
    if value is None:
        quality = summary.get("quality", {})
        value = quality.get(name) if isinstance(quality, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def evaluate_gates(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    gates: QualityGates,
) -> dict[str, Any]:
    """Evaluate configured blocking and observatory gates without model calls.

    Rates are represented as fractions in reports; category pass rates remain
    percentages for compatibility with the existing report schema.
    """
    baseline_summary = baseline.get("summary", {})
    candidate_summary = candidate.get("summary", {})
    failures: list[str] = []
    observations: list[str] = []

    safety_rate = _summary_metric(candidate_summary, "safety_pass_rate")
    if safety_rate is None:
        failures.append("missing safety_pass_rate")
    elif safety_rate < gates.blocking.safety_pass_rate:
        failures.append(
            f"safety pass rate {safety_rate:.4f} below {gates.blocking.safety_pass_rate:.4f}"
        )

    hallucination_rate = _summary_metric(candidate_summary, "hallucination_rate")
    if hallucination_rate is None:
        failures.append("missing hallucination_rate")
    elif hallucination_rate > gates.blocking.hallucination_rate_max:
        failures.append(
            f"hallucination rate {hallucination_rate:.4f} above {gates.blocking.hallucination_rate_max:.4f}"
        )

    base_categories = baseline_summary.get("category_pass_rates", baseline_summary.get("categories", {}))
    candidate_categories = candidate_summary.get("category_pass_rates", candidate_summary.get("categories", {}))
    category_deltas: dict[str, float | None] = {}
    for name in sorted(set(base_categories) | set(candidate_categories)):
        old, new = base_categories.get(name), candidate_categories.get(name)
        delta = round(float(new) - float(old), 2) if old is not None and new is not None else None
        category_deltas[name] = delta
        if delta is None:
            failures.append(f"missing category rate for {name}")
        elif delta < -gates.blocking.category_regression_max_pp:
            failures.append(
                f"category {name} regressed by {abs(delta):.2f} pp "
                f"(limit {gates.blocking.category_regression_max_pp:.2f} pp)"
            )

    for name, target in (
        ("final_correctness", gates.observatory.final_correctness_target),
        ("key_steps_hit_rate", gates.observatory.key_steps_hit_target),
        ("complete_answer_rate", gates.observatory.complete_answer_target),
    ):
        value = _summary_metric(candidate_summary, name)
        if value is None:
            observations.append(f"missing observatory metric {name}")
        elif value < target:
            observations.append(f"{name} {value:.4f} below target {target:.4f}")

    return {
        "status": "rejected" if failures else "approved",
        "failures": sorted(set(failures)),
        "observations": sorted(set(observations)),
        "category_deltas": category_deltas,
    }
