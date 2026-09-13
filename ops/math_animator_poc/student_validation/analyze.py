"""Aggregate the anonymous T15 static-versus-animation study."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


CONCEPTS = {"secant_tangent", "riemann_sum", "taylor_approximation"}
CONDITIONS = {"static", "animation"}


def _as_bool(value: str, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no", ""}:
        return False
    raise ValueError(f"row {row_number}: {field} must be true/false")


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {
            "participant_id",
            "concept",
            "condition",
            "order",
            "correct",
            "duration_seconds",
            "helpfulness",
            "adverse_effect",
            "severe_adverse",
            "notes",
        }
        if set(reader.fieldnames or ()) != required:
            raise ValueError("CSV columns do not match responses-template.csv")

        seen: set[tuple[str, str, str]] = set()
        for row_number, raw in enumerate(reader, start=2):
            participant_id = raw["participant_id"].strip()
            concept = raw["concept"].strip()
            condition = raw["condition"].strip()
            if not participant_id or len(participant_id) > 64:
                raise ValueError(f"row {row_number}: invalid participant_id")
            if concept not in CONCEPTS:
                raise ValueError(f"row {row_number}: unknown concept")
            if condition not in CONDITIONS:
                raise ValueError(f"row {row_number}: unknown condition")

            key = (participant_id, concept, condition)
            if key in seen:
                raise ValueError(f"row {row_number}: duplicate participant/concept/condition")
            seen.add(key)

            order = int(raw["order"])
            correct = int(raw["correct"])
            duration = float(raw["duration_seconds"])
            if order not in {1, 2} or correct not in {0, 1} or duration <= 0:
                raise ValueError(f"row {row_number}: invalid order/correct/duration")

            helpfulness_text = raw["helpfulness"].strip()
            helpfulness = int(helpfulness_text) if helpfulness_text else None
            if condition == "animation" and helpfulness not in {1, 2, 3, 4, 5}:
                raise ValueError(f"row {row_number}: animation helpfulness must be 1-5")
            if condition == "static" and helpfulness is not None:
                raise ValueError(f"row {row_number}: static helpfulness must be empty")

            rows.append(
                {
                    "participant_id": participant_id,
                    "concept": concept,
                    "condition": condition,
                    "order": order,
                    "correct": correct,
                    "duration_seconds": duration,
                    "helpfulness": helpfulness,
                    "adverse_effect": _as_bool(raw["adverse_effect"], "adverse_effect", row_number),
                    "severe_adverse": _as_bool(raw["severe_adverse"], "severe_adverse", row_number),
                }
            )
    return rows


def analyze(rows: list[dict[str, object]]) -> dict[str, object]:
    participant_cells: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        participant_cells[str(row["participant_id"])].add(
            (str(row["concept"]), str(row["condition"]))
        )

    expected = {(concept, condition) for concept in CONCEPTS for condition in CONDITIONS}
    complete_participants = {
        participant_id
        for participant_id, cells in participant_cells.items()
        if cells == expected
    }
    complete_rows = [
        row for row in rows if str(row["participant_id"]) in complete_participants
    ]

    by_condition = {
        condition: [row for row in complete_rows if row["condition"] == condition]
        for condition in CONDITIONS
    }
    metrics: dict[str, dict[str, float]] = {}
    for condition, condition_rows in by_condition.items():
        metrics[condition] = {
            "accuracy": (
                sum(int(row["correct"]) for row in condition_rows) / len(condition_rows)
                if condition_rows
                else 0.0
            ),
            "median_duration_seconds": (
                statistics.median(float(row["duration_seconds"]) for row in condition_rows)
                if condition_rows
                else 0.0
            ),
        }

    animation_rows = by_condition["animation"]
    helpful_rate = (
        sum(int(row["helpfulness"] or 0) >= 4 for row in animation_rows) / len(animation_rows)
        if animation_rows
        else 0.0
    )
    adverse_rate = (
        sum(bool(row["adverse_effect"]) for row in animation_rows) / len(animation_rows)
        if animation_rows
        else 0.0
    )
    severe_adverse_count = sum(bool(row["severe_adverse"]) for row in animation_rows)

    static_accuracy = metrics["static"]["accuracy"]
    animation_accuracy = metrics["animation"]["accuracy"]
    static_duration = metrics["static"]["median_duration_seconds"]
    animation_duration = metrics["animation"]["median_duration_seconds"]
    accuracy_gain = animation_accuracy - static_accuracy
    time_reduction = (
        (static_duration - animation_duration) / static_duration if static_duration else 0.0
    )

    sample_complete = len(complete_participants) >= 8
    primary_effect = accuracy_gain >= 0.10 or (
        time_reduction >= 0.15 and animation_accuracy >= static_accuracy
    )
    gate_passed = (
        sample_complete
        and primary_effect
        and helpful_rate >= 0.70
        and adverse_rate <= 0.20
        and severe_adverse_count == 0
    )

    return {
        "gate_passed": gate_passed,
        "complete_participants": len(complete_participants),
        "excluded_incomplete_participants": len(participant_cells) - len(complete_participants),
        "metrics": metrics,
        "accuracy_gain_percentage_points": round(accuracy_gain * 100, 2),
        "median_time_reduction_percent": round(time_reduction * 100, 2),
        "animation_helpful_rate_percent": round(helpful_rate * 100, 2),
        "animation_adverse_rate_percent": round(adverse_rate * 100, 2),
        "severe_adverse_count": severe_adverse_count,
        "checks": {
            "sample_complete": sample_complete,
            "primary_effect": primary_effect,
            "helpful_rate": helpful_rate >= 0.70,
            "adverse_rate": adverse_rate <= 0.20,
            "no_severe_adverse": severe_adverse_count == 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(load_rows(args.csv_path)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

