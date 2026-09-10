"""Versioned JSON/Markdown reports and baseline comparisons."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import CaseResult, RunReport
from .scoring import REASONING_DEFECT_DIMENSIONS, WEIGHTS


def _average(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def summarise_results(results: list[CaseResult]) -> dict[str, Any]:
    dimension_values: dict[str, list[float]] = defaultdict(list)
    category_values: dict[str, list[float]] = defaultdict(list)
    category_passes: dict[str, list[bool]] = defaultdict(list)
    mode_values: dict[str, list[float]] = defaultdict(list)
    latencies: list[float] = []
    costs: list[float] = []
    total_tokens: list[float] = []
    hard_failures: list[dict[str, Any]] = []
    human_review_cases: set[str] = set()
    defect_cases: dict[str, list[str]] = defaultdict(list)
    defect_failures: dict[str, list[str]] = defaultdict(list)
    defect_model_cells: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        category_values[result.category.value].append(result.weighted_score)
        category_passes[result.category.value].append(not result.hard_failures and result.weighted_score >= 80)
        mode_values[result.tutor_mode.value].append(result.weighted_score)
        for name, dimension in result.dimensions.items():
            if dimension.score is not None:
                dimension_values[name].append(dimension.score)
            if dimension.needs_human_review:
                human_review_cases.add(result.case_id)
        execution = result.execution
        if execution.latency_ms is not None:
            latencies.append(float(execution.latency_ms))
        if execution.estimated_cost is not None:
            costs.append(execution.estimated_cost)
        if execution.token_usage and execution.token_usage.get("total_tokens") is not None:
            total_tokens.append(float(execution.token_usage["total_tokens"]))
        if result.hard_failures:
            hard_failures.append({"case_id": result.case_id, "failures": result.hard_failures})
        failure_class = result.expected_failure_class.value
        defect_cases[failure_class].append(result.case_id)
        if failure_class in REASONING_DEFECT_DIMENSIONS:
            dimension_name = REASONING_DEFECT_DIMENSIONS[failure_class]
            dimension = result.dimensions[dimension_name]
            passed = dimension.score == 100.0
            model = result.execution.model or "unknown"
            defect_model_cells[model][failure_class].append(passed)
            if not passed:
                defect_failures[failure_class].append(result.case_id)
    defect_classes = sorted(set(defect_cases) | set(REASONING_DEFECT_DIMENSIONS))
    defect_models = {
        model: {
            name: {
                "case_count": len(values),
                "failure_count": len(values) - sum(values),
                "pass_rate": round(100 * sum(values) / len(values), 2) if values else None,
            }
            for name in defect_classes
            if (values := cells.get(name, []))
        }
        for model, cells in sorted(defect_model_cells.items())
    }
    return {
        "case_count": len(results),
        "weighted_score": _average([result.weighted_score for result in results]),
        "dimensions": {name: _average(values) for name, values in sorted(dimension_values.items())},
        "categories": {name: _average(values) for name, values in sorted(category_values.items())},
        "category_pass_rates": {
            name: round(100 * sum(values) / len(values), 2)
            for name, values in sorted(category_passes.items())
        },
        "tutor_modes": {name: _average(values) for name, values in sorted(mode_values.items())},
        "hard_failures": hard_failures,
        "hard_failure_count": len(hard_failures),
        "human_review_cases": sorted(human_review_cases),
        "latency": {"p95_ms": _percentile(latencies, 0.95), "average_ms": _average(latencies)},
        "cost": {"average": _average(costs), "reported_cases": len(costs)},
        "tokens": {"average_total": _average(total_tokens), "reported_cases": len(total_tokens)},
        "reasoning_defects": {
            "class_counts": {name: len(defect_cases.get(name, [])) for name in defect_classes},
            "case_ids": {name: sorted(defect_cases.get(name, [])) for name in defect_classes},
            "failure_counts": {name: len(defect_failures.get(name, [])) for name in defect_classes},
            "failure_case_ids": {name: sorted(defect_failures.get(name, [])) for name in defect_classes},
            "by_model": defect_models,
        },
    }


def build_run_report(
    *,
    run_id: str,
    label: str,
    mode: str,
    git_sha: str,
    dataset_version: str,
    dataset_hash: str,
    results: list[CaseResult],
    model: str | None,
    prompt_version: str | None,
    schema_version: str = "1.0",
    schema_hash: str | None = None,
    case_hashes: dict[str, str] | None = None,
    model_provider: str | None = None,
    safety_filter_version: str | None = None,
    environment: dict[str, Any] | None = None,
    status: str | None = None,
    reason: str | None = None,
    full_dataset: bool = True,
    selected_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    summary = summarise_results(results)
    report_status = status or ("mocked_pass" if mode == "mocked" and not summary["hard_failures"] else "baseline_only")
    if mode == "live" and results:
        missing_telemetry = any(
            result.execution.model is None
            or result.execution.prompt_version is None
            or result.execution.token_usage is None
            or result.execution.estimated_cost is None
            or result.execution.latency_ms is None
            for result in results
        )
        if missing_telemetry:
            report_status = "incomplete"
        elif summary["hard_failure_count"]:
            report_status = "rejected"
        elif summary["human_review_cases"]:
            report_status = "needs_human_review"
        else:
            report_status = "baseline_only"
    payload = {
        "report_schema_version": "1.0",
        "run_id": run_id,
        "label": label,
        "mode": mode,
        "status": report_status,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "dataset_version": dataset_version,
        "dataset_hash": dataset_hash,
        "schema_version": schema_version,
        "schema_hash": schema_hash,
        "case_hashes": case_hashes or {},
        "model_provider": model_provider,
        "model": model,
        "prompt_version": prompt_version,
        "safety_filter_version": safety_filter_version,
        "environment": environment or {},
        "full_dataset": full_dataset,
        "selected_case_ids": selected_case_ids or [result.case_id for result in results],
        "summary": summary,
        "results": [result.model_dump(mode="json") for result in results],
    }
    return RunReport.model_validate(payload).model_dump(mode="json")


def apply_human_reviews(report: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    if report.get("mode") != "live":
        raise ValueError("human quality review can only be applied to a live report")
    reviewer = str(review.get("reviewer") or "").strip()
    if len(reviewer) < 3 or reviewer.startswith("step3.4-"):
        raise ValueError("an accountable human reviewer identifier is required")
    review_cases = review.get("cases")
    if not isinstance(review_cases, dict):
        raise ValueError("review file must contain a cases mapping")
    updated = json.loads(json.dumps(report, ensure_ascii=False))
    missing: list[str] = []
    for result in updated.get("results", []):
        case_review = review_cases.get(result["case_id"], {})
        dimensions = result.get("dimensions", {})
        for name, dimension in dimensions.items():
            if not dimension.get("needs_human_review"):
                continue
            item = case_review.get(name)
            if not isinstance(item, dict) or item.get("score") not in {0, 1, 2} or not str(item.get("note") or "").strip():
                missing.append(f"{result['case_id']}:{name}")
                continue
            dimension["score"] = float(item["score"] * 50)
            dimension["evidence"].append(f"human review by {reviewer}: {item['note']}")
            dimension["needs_human_review"] = False
        scored = [
            (WEIGHTS[name], value.get("score"))
            for name, value in dimensions.items()
            if name in WEIGHTS and value.get("score") is not None
        ]
        result["weighted_score"] = round(
            sum(weight * score for weight, score in scored) / sum(weight for weight, _ in scored), 2
        ) if scored else 0.0
    if missing:
        raise ValueError(f"human review is incomplete: {', '.join(missing[:10])}")
    validated = [CaseResult.model_validate(item) for item in updated.get("results", [])]
    updated["summary"] = summarise_results(validated)
    updated["human_review"] = {
        "reviewer": reviewer,
        "note": str(review.get("note") or "").strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    if updated["summary"]["hard_failure_count"]:
        updated["status"] = "rejected"
    else:
        telemetry_missing = any(
            item["execution"].get("model") is None
            or item["execution"].get("prompt_version") is None
            or item["execution"].get("token_usage") is None
            or item["execution"].get("estimated_cost") is None
            or item["execution"].get("latency_ms") is None
            for item in updated.get("results", [])
        )
        updated["status"] = "incomplete" if telemetry_missing else "baseline_only"
    return RunReport.model_validate(updated).model_dump(mode="json")


def build_human_review_template(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("mode") != "live":
        raise ValueError("human quality review templates can only be generated for live reports")
    cases: dict[str, Any] = {}
    for result in report.get("results", []):
        pending = {
            name: {"score": None, "note": ""}
            for name, dimension in result.get("dimensions", {}).items()
            if dimension.get("needs_human_review")
        }
        if pending:
            cases[result["case_id"]] = pending
    return {
        "run_id": report.get("run_id"),
        "dataset_hash": report.get("dataset_hash"),
        "reviewer": "",
        "note": "",
        "rubric": {0: "不通过", 1: "部分通过", 2: "通过"},
        "cases": cases,
    }


def _regression(current: float | None, baseline: float | None, allowed_drop: float) -> bool:
    return current is not None and baseline is not None and current < baseline - allowed_drop


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    allow_cost_regression: bool = False,
    cost_exception_note: str | None = None,
) -> dict[str, Any]:
    if baseline.get("dataset_hash") != candidate.get("dataset_hash"):
        raise ValueError("baseline and candidate dataset hashes differ")
    base_summary, candidate_summary = baseline["summary"], candidate["summary"]
    failures: list[str] = []
    if baseline.get("mode") and baseline.get("mode") != "live":
        failures.append("release comparison requires a live baseline")
    if candidate.get("mode") and candidate.get("mode") != "live":
        failures.append("release comparison requires a live candidate")
    if baseline.get("status") and baseline.get("status") != "approved":
        failures.append("baseline must be human-approved before comparison")
    if not baseline.get("full_dataset", True) or not candidate.get("full_dataset", True):
        failures.append("filtered runs cannot be used for release comparison")
    if candidate_summary.get("hard_failure_count", 0):
        failures.append("candidate contains hard failures")
    if _regression(candidate_summary.get("weighted_score"), base_summary.get("weighted_score"), 1.0):
        failures.append("weighted score regressed by more than 1 point")
    dimension_deltas: dict[str, float | None] = {}
    for name in sorted(set(base_summary.get("dimensions", {})) | set(candidate_summary.get("dimensions", {}))):
        old, new = base_summary.get("dimensions", {}).get(name), candidate_summary.get("dimensions", {}).get(name)
        dimension_deltas[name] = round(new - old, 2) if old is not None and new is not None else None
        if _regression(new, old, 5.0):
            failures.append(f"dimension {name} regressed by more than 5 points")
    category_deltas: dict[str, float | None] = {}
    base_category_rates = base_summary.get("category_pass_rates", base_summary.get("categories", {}))
    candidate_category_rates = candidate_summary.get("category_pass_rates", candidate_summary.get("categories", {}))
    for name in sorted(set(base_category_rates) | set(candidate_category_rates)):
        old, new = base_category_rates.get(name), candidate_category_rates.get(name)
        category_deltas[name] = round(new - old, 2) if old is not None and new is not None else None
        if _regression(new, old, 10.0):
            failures.append(f"category {name} regressed by more than 10 points")
    base_p95 = base_summary.get("latency", {}).get("p95_ms")
    candidate_p95 = candidate_summary.get("latency", {}).get("p95_ms")
    if base_p95 and candidate_p95 and candidate_p95 > base_p95 * 1.2:
        failures.append("P95 latency increased by more than 20 percent")
    base_cost = base_summary.get("cost", {}).get("average")
    candidate_cost = candidate_summary.get("cost", {}).get("average")
    if base_cost and candidate_cost and candidate_cost > base_cost * 1.15 and not allow_cost_regression:
        failures.append("average cost increased by more than 15 percent")
    if allow_cost_regression and (not cost_exception_note or len(cost_exception_note.strip()) < 10):
        failures.append("cost regression exception requires a substantive human review note")
    if candidate.get("status") in {"incomplete", "needs_human_review"}:
        failures.append("candidate telemetry or human review is incomplete")
    return {
        "comparison_schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hash": candidate["dataset_hash"],
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "status": "rejected" if failures else "approved",
        "failures": sorted(set(failures)),
        "weighted_score_delta": (
            round(candidate_summary["weighted_score"] - base_summary["weighted_score"], 2)
            if candidate_summary.get("weighted_score") is not None and base_summary.get("weighted_score") is not None
            else None
        ),
        "dimension_deltas": dimension_deltas,
        "category_deltas": category_deltas,
        "latency_p95_delta_ms": (
            round(candidate_p95 - base_p95, 2) if candidate_p95 is not None and base_p95 is not None else None
        ),
        "average_cost_delta": (
            round(candidate_cost - base_cost, 8) if candidate_cost is not None and base_cost is not None else None
        ),
        "cost_exception": (
            {"allowed": True, "note": cost_exception_note}
            if allow_cost_regression
            else None
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# 模型质量评测报告：{report.get('label')}",
        "",
        f"- 状态：`{report.get('status')}`",
        f"- Run ID：`{report.get('run_id')}`",
        f"- Dataset：`{report.get('dataset_version')}` / `{report.get('dataset_hash')}`",
        f"- Schema：`{report.get('schema_version')}` / `{report.get('schema_hash')}`",
        f"- Git SHA：`{report.get('git_sha')}`",
        f"- Provider / Model / Prompt：`{report.get('model_provider')}` / `{report.get('model')}` / `{report.get('prompt_version')}`",
        f"- 案例数：{summary.get('case_count', 0)}",
        f"- 加权分：{summary.get('weighted_score')}",
        f"- 硬失败案例数：{summary.get('hard_failure_count', 0)}",
        f"- P95 延迟：{summary.get('latency', {}).get('p95_ms')} ms",
        f"- 平均成本：{summary.get('cost', {}).get('average')}",
        "",
        "## 维度得分",
        "",
        "| 维度 | 得分 |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {score} |" for name, score in summary.get("dimensions", {}).items())
    defects = summary.get("reasoning_defects", {})
    lines.extend(["", "## 推理缺陷类型 × 模型", ""])
    defect_names = list(REASONING_DEFECT_DIMENSIONS)
    lines.append("| 模型 | " + " | ".join(defect_names) + " |")
    lines.append("|---|" + "---:|" * len(defect_names))
    for model, cells in defects.get("by_model", {}).items():
        values = []
        for name in defect_names:
            cell = cells.get(name)
            values.append(
                f"{cell['failure_count']}/{cell['case_count']} 失败（通过率 {cell['pass_rate']}%）"
                if cell else "无用例"
            )
        lines.append(f"| {model} | " + " | ".join(values) + " |")
    lines.extend(["", "### 缺陷用例清单", ""])
    for name in defect_names:
        count = defects.get("class_counts", {}).get(name, 0)
        failures = defects.get("failure_case_ids", {}).get(name, [])
        lines.append(f"- `{name}`：标记 {count} 条；检测失败 {len(failures)} 条：{', '.join(failures) or '无'}")
    lines.extend(["", "## 硬失败", ""])
    if summary.get("hard_failures"):
        lines.extend(f"- `{item['case_id']}`：{', '.join(item['failures'])}" for item in summary["hard_failures"])
    else:
        lines.append("- 无")
    lines.extend(["", "## 稳定性复跑", ""])
    if report.get("stability_summary"):
        lines.extend(
            f"- `{item['case_id']}`：分数范围 {item['score_min']}–{item['score_max']}，"
            f"响应变体 {item['unique_response_count']}，硬失败一致={item['hard_failure_consistent']}"
            for item in report["stability_summary"]
        )
    else:
        lines.append("- 无需复跑")
    return "\n".join(lines) + "\n"


def comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# 模型 / Prompt 前后对比",
        "",
        f"- 状态：`{comparison['status']}`",
        f"- Baseline：`{comparison['baseline_run_id']}`",
        f"- Candidate：`{comparison['candidate_run_id']}`",
        f"- 加权分变化：{comparison['weighted_score_delta']}",
        f"- P95 延迟变化：{comparison['latency_p95_delta_ms']} ms",
        f"- 平均成本变化：{comparison['average_cost_delta']}",
        "",
        "## 门禁结论",
        "",
    ]
    lines.extend(f"- {failure}" for failure in comparison["failures"] or ["全部门禁通过"])
    return "\n".join(lines) + "\n"


def load_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunReport.model_validate(payload).model_dump(mode="json")
