"""v2 评测 runner(mocked 模式)。

mocked 运行不调用任何模型:应答按 case 的确定性 oracle 构造(与 v1 mocked
同约定),用于验证 评分器→门禁→报告对比 的管线完整性。mocked 全绿只证明
管线可用,不能据此宣称线上模型质量(与 audit-v2 同一口径)。

live 模式留待正式标注集就绪后接入(1-J)。
"""

from __future__ import annotations

from typing import Any, Iterable

from .v2_schema import V2Case
from .v2_scoring import V2CaseScore, V2ToolTrace, score_v2_case, summarise_v2_scores

REPORT_SCHEMA_VERSION = "2.0"


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
    return {
        "comparison_schema_version": "2.0",
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "mode": candidate.get("mode"),
        **verdict,
    }
