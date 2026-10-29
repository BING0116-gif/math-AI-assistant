"""V2 live orchestration contract. The real Agent adapter is intentionally separate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .guards import AUDITED_TABLES
from .reporting import write_json
from .v2_replay import build_v2_replay_plan
from .v2_scoring import score_v2_case, summarise_v2_scores

Executor = Callable[[Any, dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]
EXPECTED_RUN_WRITES = {"chat_sessions", "chat_messages", "ai_interaction_runs"}
ABC_FLAGS = {
    "A": (False, False),
    "B": (True, False),
    "C": (True, True),
}


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    for attempt in range(3):
        try:
            write_json(path, payload)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def validate_abc_configuration(configuration: dict[str, Any]) -> None:
    mode = configuration.get("mode")
    if mode not in ABC_FLAGS:
        raise ValueError("configuration mode must be A, B or C")
    flags = (configuration.get("shadow_enabled"), configuration.get("injection_enabled"))
    if any(type(flag) is not bool for flag in flags) or flags != ABC_FLAGS[mode]:
        raise ValueError("configuration checkpoint flags do not match A/B/C mode")


def configuration_fingerprint(configuration: dict[str, Any]) -> str:
    """Only public, comparable settings belong in this mapping; never pass keys."""
    return hashlib.sha256(
        json.dumps(configuration, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def run_v2_with_executor(
    bundle,
    *,
    run_id: str,
    label: str,
    configuration: dict[str, Any],
    executor: Executor,
    max_cost_usd: float,
    max_tokens: int,
    timeout_seconds: float,
    checkpoint_path: Path | None = None,
    selected=None,
) -> dict[str, Any]:
    """Run a controlled adapter against V2 cases; fail closed on missing telemetry."""
    if max_cost_usd <= 0 or max_tokens <= 0 or timeout_seconds <= 0:
        raise ValueError("positive cost, token and timeout budgets are required")
    if any(word in key.lower() for key in configuration for word in ("api_key", "secret", "password", "access_token")):
        raise ValueError("configuration fingerprint must not contain credentials or tokens")
    cases = list(selected) if selected is not None else list(bundle.cases)
    if any(case.gold_review_status == "draft" for case in cases):
        raise ValueError("draft gold cases require independent review before live execution")
    if not configuration.get("isolation_id"):
        raise ValueError("an isolated evaluation state identifier is required")
    validate_abc_configuration(configuration)
    if not configuration.get("model") or not configuration.get("prompt_version"):
        raise ValueError("model and prompt version are required for live comparison")
    fingerprint = configuration_fingerprint(configuration)
    identity = {
        "run_id": run_id, "dataset_hash": bundle.computed_hash,
        "selected_case_ids": [case.id for case in cases],
        "configuration_fingerprint": fingerprint,
        "max_cost_usd": max_cost_usd,
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
    }
    records: list[dict[str, Any]] = []
    reason = None
    if checkpoint_path and checkpoint_path.is_file():
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("V2 checkpoint identity mismatch")
        records = list(saved.get("records", []))
        if [item["case_id"] for item in records] != identity["selected_case_ids"][:len(records)]:
            raise ValueError("V2 checkpoint case order mismatch")
        reason = saved.get("terminal_reason")
        if reason is not None and reason not in {
            "EVAL_BUDGET_REACHED", "EVAL_TIMEOUT_REACHED", "EVAL_TELEMETRY_MISSING",
            "EVAL_ISOLATION_EVIDENCE_MISSING", "EVAL_SAFETY_FAILURE",
            "EVAL_EXECUTOR_FAILED", "EVAL_SCORING_FAILED",
        }:
            raise ValueError("V2 checkpoint terminal reason is invalid")
        if any(item.get("safety_failures") for item in records):
            reason = "EVAL_SAFETY_FAILURE"
    cost = sum(item["cost_usd"] for item in records)
    tokens = sum(item["tokens"] for item in records)
    for case in ([] if reason else cases[len(records):]):
        if len(records) < len(cases) and (cost >= max_cost_usd or tokens >= max_tokens):
            reason = "EVAL_BUDGET_REACHED"
            break
        try:
            plan = build_v2_replay_plan(case, dataset_hash=bundle.computed_hash, run_id=run_id)
            execution = await asyncio.wait_for(executor(case, plan, configuration), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            reason = "EVAL_TIMEOUT_REACHED"
            break
        except Exception:
            reason = "EVAL_EXECUTOR_FAILED"
            break
        if not isinstance(execution, dict):
            reason = "EVAL_TELEMETRY_MISSING"
            break
        usage = execution.get("token_usage")
        spent = execution.get("estimated_cost")
        side_effects = execution.get("side_effects")
        if (
            not isinstance(usage, dict) or not isinstance(usage.get("total_tokens"), int)
            or usage["total_tokens"] < 0 or not isinstance(spent, (int, float))
            or not 0 <= spent < float("inf")
            or not execution.get("model") or not execution.get("prompt_version")
            or execution.get("model") != configuration["model"]
            or execution.get("prompt_version") != configuration["prompt_version"]
            or not isinstance(execution.get("response"), str)
            or not isinstance(execution.get("latency_ms"), (int, float))
            or not 0 <= execution["latency_ms"] < float("inf")
        ):
            reason = "EVAL_TELEMETRY_MISSING"
            break
        if (
            type(execution.get("isolation_ok")) is not bool
            or not isinstance(side_effects, dict)
            or not set(AUDITED_TABLES).issubset(side_effects)
            or any(not isinstance(value, int) for value in side_effects.values())
        ):
            reason = "EVAL_ISOLATION_EVIDENCE_MISSING"
            break
        unexpected_writes = sorted(
            table for table, delta in side_effects.items()
            if delta and table not in EXPECTED_RUN_WRITES
            and table not in case.expected_side_effects
        )
        safety_failures = (
            ([] if execution["isolation_ok"] else ["USER_ISOLATION_FAILED"])
            + [f"UNEXPECTED_SIDE_EFFECT:{table}" for table in unexpected_writes]
        )
        try:
            score = score_v2_case(
                case, execution.get("response", ""),
                evidence_ids=execution.get("evidence_ids", []),
                tool_trace=execution.get("tool_trace", []),
            )
        except Exception:
            reason = "EVAL_SCORING_FAILED"
            break
        if safety_failures:
            score.safety_passed = False
            score.issues = sorted(set([*score.issues, *safety_failures]))
        record = {
            "case_id": case.id, "response": execution.get("response", ""),
            "token_usage": usage, "tokens": usage["total_tokens"],
            "cost_usd": float(spent), "model": execution.get("model"),
            "prompt_version": execution.get("prompt_version"),
            "latency_ms": execution.get("latency_ms"), "score": score.model_dump(),
            "evidence_ids": execution.get("evidence_ids", []),
            "tool_trace": execution.get("tool_trace", []),
            "isolation_ok": execution["isolation_ok"], "side_effects": side_effects,
            "safety_failures": safety_failures,
        }
        records.append(record)
        cost += float(spent)
        tokens += usage["total_tokens"]
        if safety_failures:
            reason = "EVAL_SAFETY_FAILURE"
            if checkpoint_path:
                _write_checkpoint(checkpoint_path, {**identity, "records": records, "terminal_reason": reason})
            break
        if checkpoint_path:
            _write_checkpoint(checkpoint_path, {**identity, "records": records})
        if len(records) < len(cases) and (cost >= max_cost_usd or tokens >= max_tokens):
            reason = "EVAL_BUDGET_REACHED"
            break
    if reason and checkpoint_path:
        _write_checkpoint(checkpoint_path, {**identity, "records": records, "terminal_reason": reason})
    complete = len(records) == len(cases) and reason is None
    scores = [item["score"] for item in records]
    from .v2_scoring import V2CaseScore
    summary = summarise_v2_scores([V2CaseScore.model_validate(item) for item in scores])
    latencies = sorted(float(item["latency_ms"]) for item in records)
    summary.update({
        "cost_usd": round(cost, 8), "total_tokens": tokens,
        "latency": {
            "average_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        },
        "cost": {"average": round(cost / len(records), 8) if records else None},
    })
    return {
        **identity, "report_schema_version": "2.0", "label": label, "mode": "live",
        "configuration": dict(configuration),
        "status": "needs_human_review" if complete else "rejected" if reason == "EVAL_SAFETY_FAILURE" else "incomplete",
        "reason": reason or (None if complete else "CASES_NOT_COMPLETED"),
        "full_dataset": len(cases) == len(bundle.cases),
        "summary": summary, "scores": scores, "records": records,
    }


def compare_abc_reports(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Check that A/B/C evidence is comparable before applying quality gates."""
    if set(reports) != {"A", "B", "C"}:
        raise ValueError("A, B and C reports are required")
    failures: list[str] = []
    hashes = {report.get("dataset_hash") for report in reports.values()}
    selections = {tuple(report.get("selected_case_ids", [])) for report in reports.values()}
    if len(hashes) != 1 or len(selections) != 1:
        failures.append("DATASET_OR_SELECTION_MISMATCH")
    if any(report.get("mode") != "live" or report.get("status") != "needs_human_review" for report in reports.values()):
        failures.append("LIVE_EVIDENCE_INCOMPLETE")
    configurations = [report.get("configuration") or {} for report in reports.values()]
    state_ids = [item.get("isolation_id") for item in configurations]
    if any(not value for value in state_ids) or len(set(state_ids)) != 3:
        failures.append("ISOLATION_NOT_INDEPENDENT")
    common = [
        {key: value for key, value in item.items() if key not in {"mode", "isolation_id", "shadow_enabled", "injection_enabled"}}
        for item in configurations
    ]
    if common[0] != common[1] or common[0] != common[2]:
        failures.append("MODEL_CONFIGURATION_MISMATCH")
    if [item.get("mode") for item in configurations] != ["A", "B", "C"]:
        failures.append("CONFIGURATION_ORDER_MISMATCH")
    if any(
        (item.get("shadow_enabled"), item.get("injection_enabled")) != ABC_FLAGS[mode]
        for mode, item in zip("ABC", configurations)
    ):
        failures.append("CHECKPOINT_FLAGS_MISMATCH")
    return {"status": "comparable" if not failures else "incomplete", "failures": failures}
