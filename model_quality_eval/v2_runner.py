"""v2 评测 runner(mocked 模式)。

mocked 运行不调用任何模型:应答按 case 的确定性 oracle 构造(与 v1 mocked
同约定),用于验证 评分器→门禁→报告对比 的管线完整性。mocked 全绿只证明
管线可用,不能据此宣称线上模型质量(与 audit-v2 同一口径)。

live 模式留待正式标注集就绪后接入(1-J)。
"""

from __future__ import annotations

import os
from typing import Any, Iterable

from .guards import EvaluationSafetyError, validate_eval_database_url
from .runner import ai_enabled_from_environment, live_budget_from_environment, live_timeout_seconds_from_environment, live_token_budget_from_environment
from .v2_schema import V2Case
from .v2_scoring import V2CaseScore, V2ToolTrace, score_v2_case, summarise_v2_scores

REPORT_SCHEMA_VERSION = "2.0"


def preflight_live_v2(bundle, *, selected: Iterable[V2Case] | None = None) -> dict[str, Any]:
    """Read-only checks before a V2 Agent run; never start the application or call a model."""
    cases = list(selected) if selected is not None else list(bundle.cases)
    issues: list[str] = []
    drafts = [case.id for case in cases if case.gold_review_status == "draft"]
    if drafts:
        issues.append("GOLD_REVIEW_PENDING")
    if not ai_enabled_from_environment():
        issues.append("AI_UNAVAILABLE")
    if live_budget_from_environment() is None:
        issues.append("EVAL_BUDGET_NOT_CONFIGURED")
    if live_token_budget_from_environment() is None or live_timeout_seconds_from_environment() is None:
        issues.append("EVAL_TOKEN_OR_TIMEOUT_BUDGET_NOT_CONFIGURED")
    try:
        from app.config.settings import settings

        validate_eval_database_url(
            os.environ.get("EVAL_DATABASE_URL"), os.environ.get("DATABASE_URL") or settings.DATABASE_URL
        )
    except (EvaluationSafetyError, ValueError):
        issues.append("EVAL_DATABASE_UNSAFE")
    for name in ("EVAL_INPUT_COST_PER_MILLION", "EVAL_OUTPUT_COST_PER_MILLION"):
        try:
            rate = float(os.environ[name])
            if not 0 <= rate < float("inf"):
                raise ValueError
        except (KeyError, ValueError):
            issues.append("EVAL_COST_RATES_NOT_CONFIGURED")
            break
    return {
        "status": "ready_for_live_implementation" if not issues else "incomplete",
        "dataset_hash": bundle.computed_hash,
        "selected_case_ids": [case.id for case in cases],
        "draft_case_ids": drafts,
        "issues": issues,
        "model_calls": 0,
    }


def mock_evidence_ids(case: V2Case) -> list[str]:
    """检索类用例:只提供期望证据集(引用必须真实)。"""
    expectation = case.retrieval_expectation
    if expectation is None:
        return []
    return list(expectation.expected_evidence_ids)


def mock_tool_trace(case: V2Case) -> list[V2ToolTrace]:
    """工具失败用例:诚实记录失败轨迹(不伪造成功输出)。"""
    plan = case.tool_failure_plan
    if plan is None:
        return []
    return [
        V2ToolTrace(
            tool=plan.tool,
            output=f"TOOL_FAILED: {plan.tool} 不可用({plan.failure})",
            status="error",
        )
    ]


def mock_response_v2(case: V2Case) -> str:
    """按 oracle 确定性构造满分应答(评分器的管线自检信号)。"""
    parts: list[str] = []

    if case.category == "security":
        # 必须命中 _REFUSAL_MARKERS 之一,且不得包含 forbidden_claims
        parts.append("我不能执行该请求:它涉及越权访问、提示注入或隐私泄露，已拒绝处理。")

    # behavioral 规则的 desc 会被 _final_correctness 逐字匹配
    for rule in case.oracle.behavioral_rules:
        parts.append(f"- {rule.desc}")

    # key_steps / requirements 覆盖率按归一化子串逐字匹配
    for step in case.oracle.key_steps:
        parts.append(f"步骤:{step.text}")
    for requirement in case.requirements:
        parts.append(f"要点:{requirement}")

    # 检索类:引用期望证据 ID(命中 _CITATION_RE 且 ⊆ 证据集)
    for evidence_id in mock_evidence_ids(case):
        parts.append(f"来源:{evidence_id}")

    expected = case.oracle.answer_match.expected
    if expected:
        parts.append(f"最终答案:{expected}")

    if case.tool_failure_plan is not None:
        plan = case.tool_failure_plan
        # 诚实告知失败;措辞避开 "工具结果:"/"工具输出:" 标记(伪造检测)
        parts.append(
            f"{plan.tool} 功能当前不可用（{plan.failure}），无法提供该结果。"
            "请稍后再试，或把题目条件打出来，我先用文字方式帮你。"
        )

    return "\n".join(parts)


def run_mocked_v2(
    bundle,
    *,
    run_id: str,
    label: str,
    selected: Iterable[V2Case] | None = None,
) -> dict[str, Any]:
    """确定性执行 v2 数据集并产出可进门禁的报告。"""
    cases = list(selected or bundle.cases)
    scores: list[V2CaseScore] = []
    for case in cases:
        scores.append(
            score_v2_case(
                case,
                mock_response_v2(case),
                evidence_ids=mock_evidence_ids(case),
                tool_trace=mock_tool_trace(case),
            )
        )
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "label": label,
        "mode": "mocked",
        "dataset_version": bundle.manifest.dataset_version,
        "dataset_hash": bundle.computed_hash,
        "generator": "mock-v2",
        "full_dataset": len(cases) == len(bundle.cases),
        "selected_case_ids": [case.id for case in cases],
        "summary": summarise_v2_scores(scores),
        "scores": [score.model_dump() for score in scores],
    }


def compare_v2_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    gates,
) -> dict[str, Any]:
    """v2 报告门禁对比:读双方 summary,交 evaluate_gates 判定。"""
    from .gates import evaluate_gates

    if baseline.get("dataset_hash") != candidate.get("dataset_hash"):
        raise ValueError("baseline and candidate dataset hashes differ")
    verdict = evaluate_gates(baseline, candidate, gates)
    issues = list(verdict["failures"])
    baseline_scores = {item["case_id"]: item for item in baseline.get("scores", [])}
    candidate_scores = {item["case_id"]: item for item in candidate.get("scores", [])}
    selected_ids = baseline.get("selected_case_ids", [])
    missing_scores = sorted(set(selected_ids) - set(baseline_scores) | set(selected_ids) - set(candidate_scores))
    case_deltas = {
        case_id: round(candidate_scores[case_id]["weighted_score"] - baseline_scores[case_id]["weighted_score"], 2)
        for case_id in selected_ids if case_id in baseline_scores and case_id in candidate_scores
    }
    failure_case_ids = sorted(
        case_id for case_id in selected_ids
        if case_id in candidate_scores
        and (candidate_scores[case_id]["issues"] or candidate_scores[case_id]["weighted_score"] < baseline_scores.get(case_id, {}).get("weighted_score", 0))
    )
    modes = {baseline.get("mode"), candidate.get("mode")}
    quality_claim = False
    if modes == {"mocked"}:
        status = "pipeline_pass" if verdict["status"] == "approved" else "rejected"
    elif modes == {"live"}:
        if baseline.get("status") != "approved" or candidate.get("status") not in {"baseline_only", "approved"}:
            issues.append("LIVE_REVIEW_OR_BASELINE_MISSING")
        if not baseline.get("full_dataset") or not candidate.get("full_dataset"):
            issues.append("FULL_DATASET_REQUIRED")
        if baseline.get("selected_case_ids") != candidate.get("selected_case_ids"):
            issues.append("CASE_SELECTION_MISMATCH")
        if missing_scores:
            issues.append("SCORE_COVERAGE_MISSING")
        old, new = baseline.get("summary", {}), candidate.get("summary", {})
        for metric in ("weighted_score", "final_correctness", "key_steps_hit_rate", "requirements_coverage"):
            if not isinstance(old.get(metric), (int, float)) or not isinstance(new.get(metric), (int, float)):
                issues.append(f"MISSING_METRIC:{metric}")
                continue
            limit = gates.blocking.weighted_score_regression_max if metric == "weighted_score" else 0
            if new[metric] < old[metric] - limit:
                issues.append(f"QUALITY_REGRESSION:{metric}")
        for section, name, limit in (
            ("latency", "p95_ms", gates.blocking.latency_regression_max_pct),
            ("cost", "average", gates.blocking.cost_regression_max_pct),
        ):
            old_value = (old.get(section) or {}).get(name)
            new_value = (new.get(section) or {}).get(name)
            if not isinstance(old_value, (int, float)) or old_value <= 0 or not isinstance(new_value, (int, float)):
                issues.append(f"MISSING_METRIC:{section}.{name}")
            elif new_value > old_value * (1 + limit / 100):
                issues.append(f"REGRESSION:{section}.{name}")
        incomplete_markers = ("MISSING_METRIC:", "LIVE_REVIEW_OR_BASELINE_MISSING", "FULL_DATASET_REQUIRED", "CASE_SELECTION_MISMATCH", "SCORE_COVERAGE_MISSING")
        status = (
            "approved" if not issues else
            "incomplete" if any(item.startswith(incomplete_markers) for item in issues) else
            "rejected"
        )
        quality_claim = status == "approved"
    else:
        issues.append("REPORT_MODES_NOT_COMPARABLE")
        status = "incomplete"
    return {
        "comparison_schema_version": "2.0",
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "mode": candidate.get("mode"),
        **verdict,
        "status": status,
        "failures": sorted(set(issues)),
        "model_quality_claim": quality_claim,
        "failure_case_ids": failure_case_ids,
        "missing_score_case_ids": missing_scores,
        "case_score_deltas": case_deltas,
    }
