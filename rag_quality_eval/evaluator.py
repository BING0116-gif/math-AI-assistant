"""Score versioned retrieval results without using an LLM as a judge."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


SENSITIVE_METADATA_KEYS = {"user_id", "owner_id", "memory_id", "session_id"}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_retrieval(gold: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    cases = {case["case_id"]: case for case in gold["cases"]}
    results = {row["case_id"]: row for row in run["results"]}
    missing = sorted(set(cases) - set(results))
    unexpected = sorted(set(results) - set(cases))
    if missing or unexpected:
        raise ValueError(f"case mismatch: missing={missing}, unexpected={unexpected}")

    top_k = int(gold.get("top_k", 5))
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    retrieved_total = 0
    forbidden_total = 0
    case_rows: list[dict[str, Any]] = []
    policy_failures: list[str] = []

    for case_id, case in cases.items():
        row = results[case_id]
        retrieved = list(row.get("retrieved_ids", []))[:top_k]
        expected = set(case.get("expected_ids", []))
        forbidden = set(case.get("forbidden_ids", []))
        hits = expected.intersection(retrieved)
        recall = len(hits) / len(expected) if expected else 1.0
        rank = next((index + 1 for index, item in enumerate(retrieved) if item in expected), None)
        reciprocal_rank = (1.0 / rank) if rank else (1.0 if not expected else 0.0)
        forbidden_hits = sorted(forbidden.intersection(retrieved))
        metadata_keys = set((row.get("metadata") or {}).keys())
        sensitive_keys = sorted(metadata_keys.intersection(SENSITIVE_METADATA_KEYS))
        expected_degraded = bool(case.get("expected_degraded", False))
        observed_degraded = bool(row.get("degraded", False))

        if forbidden_hits:
            policy_failures.append(f"{case_id}:forbidden:{','.join(forbidden_hits)}")
        if sensitive_keys:
            policy_failures.append(f"{case_id}:sensitive_metadata:{','.join(sensitive_keys)}")
        if expected_degraded != observed_degraded:
            policy_failures.append(
                f"{case_id}:degradation_expected={expected_degraded}:observed={observed_degraded}"
            )

        recall_values.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        latencies.append(float(row.get("latency_ms", 0.0)))
        retrieved_total += len(retrieved)
        forbidden_total += len(forbidden_hits)
        case_rows.append({
            "case_id": case_id,
            "kind": case["kind"],
            "recall_at_k": round(recall, 4),
            "reciprocal_rank": round(reciprocal_rank, 4),
            "forbidden_hits": forbidden_hits,
            "degraded": observed_degraded,
            "latency_ms": float(row.get("latency_ms", 0.0)),
        })

    metrics = {
        "recall_at_k": round(sum(recall_values) / len(recall_values), 4),
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
        "irrelevant_recall_rate": round(forbidden_total / retrieved_total, 4) if retrieved_total else 0.0,
        "latency_p50_ms": round(_percentile(latencies, 0.50), 2),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 2),
    }
    thresholds = gold["thresholds"]
    checks = {
        "recall_at_k": metrics["recall_at_k"] >= thresholds["min_recall_at_k"],
        "mrr": metrics["mrr"] >= thresholds["min_mrr"],
        "irrelevant_recall_rate": metrics["irrelevant_recall_rate"] <= thresholds["max_irrelevant_recall_rate"],
        "latency_p95_ms": metrics["latency_p95_ms"] <= thresholds["max_latency_p95_ms"],
        "policy": not policy_failures,
    }
    return {
        "schema_version": "1.0",
        "gold_version": gold["version"],
        "run": {
            "mode": run.get("mode", "unknown"),
            "embedding_model": run.get("embedding_model"),
            "qdrant_mode": run.get("qdrant_mode"),
            "generated_at": run.get("generated_at"),
        },
        "top_k": top_k,
        "case_count": len(case_rows),
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "policy_failures": policy_failures,
        "status": "passed" if all(checks.values()) else "failed",
        "cases": case_rows,
    }
