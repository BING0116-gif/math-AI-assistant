"""v2 mocked runner 与门禁对比回归测试。

mocked 运行是管线自检:确定性 oracle 应答应全满分;任何 0 分/幻觉/安全失败
都意味着评分器或 runner 被破坏,而不是模型质量问题。
"""

import json
import time
from pathlib import Path

import pytest

from model_quality_eval.dataset import load_v2_dataset
from model_quality_eval.gates import load_gates
from model_quality_eval.v2_runner import (
    compare_v2_reports,
    mock_response_v2,
    run_mocked_v2,
)

ROOT = Path(__file__).parents[1] / "evaluations" / "model_quality" / "v2"


@pytest.fixture(scope="module")
def bundle():
    return load_v2_dataset(str(ROOT))


def test_mocked_run_full_dataset_pipeline_selfcheck(bundle):
    """全量 95 条:oracle 确定性应答必须全满分(管线自检),耗时应远低于 5 分钟预算。"""
    started = time.perf_counter()
    report = run_mocked_v2(bundle, run_id="selfcheck-test", label="selfcheck")
    elapsed = time.perf_counter() - started

    assert report["mode"] == "mocked"
    assert report["dataset_hash"] == bundle.computed_hash
    assert report["full_dataset"] is True
    summary = report["summary"]
    assert summary["case_count"] == len(bundle.cases)
    assert summary["weighted_score"] == 100.0
    assert summary["requirements_coverage"] == 1.0
    assert summary["key_steps_hit_rate"] == 1.0
    assert summary["final_correctness"] == 1.0
    assert summary["safety_pass_rate"] == 1.0
    assert summary["hallucination_rate"] == 0.0
    assert all(rate == 100.0 for rate in summary["category_pass_rates"].values())
    # mocked 全量回归预算(路线图 3.7):< 5 分钟;确定性 runner 实际应在秒级
    assert elapsed < 300


def test_mock_response_security_refuses_without_forbidden_claims(bundle):
    for case in bundle.cases:
        if case.category != "security":
            continue
        response = mock_response_v2(case)
        assert any(marker in response for marker in ("不能", "无法", "无权", "拒绝"))
        for claim in case.oracle.forbidden_claims:
            from model_quality_eval.v2_scoring import _contains

            assert not _contains(response, claim), f"{case.id} 应答撞上禁语: {claim}"


def test_mock_response_tool_failure_is_honest(bundle):
    """工具失败用例:明确告知不可用,不触发伪造工具输出代理。"""
    from model_quality_eval.v2_scoring import score_v2_case, _contains

    for case in bundle.cases:
        if case.category != "tool_failure":
            continue
        response = mock_response_v2(case)
        assert "不可用" in response
        score = score_v2_case(
            case,
            response,
            evidence_ids=[],
            tool_trace=[
                {
                    "tool": case.tool_failure_plan.tool,
                    "output": f"TOOL_FAILED: {case.tool_failure_plan.tool}",
                    "status": "error",
                }
            ],
        )
        assert not score.hallucination_proxies["tool_output_fabricated"]
        assert "我为你找到了" not in response and "推荐以下" not in response
        assert not _contains(response, "工具结果:") and not _contains(response, "工具输出:")


def test_symbolic_fallback_matches_prime_notation(bundle):
    """f''(c) 等撇号记法 sympify 必败,退化路径必须按片段等值匹配。"""
    from model_quality_eval.scoring import answer_matches

    assert answer_matches("最终答案：f''(c)", "f''(c)", "symbolic")
    assert answer_matches("最终答案：f'(c)=0", "f'(c)=0", "symbolic")
    assert not answer_matches("最终答案：f'(c)=1", "f'(c)=0", "symbolic")


def test_compare_v2_rejects_deliberate_regression(bundle, tmp_path):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = json.loads(json.dumps(baseline))
    candidate["run_id"] = "cand"
    degraded = 0
    for score in candidate["scores"]:
        if score["category"] == "advanced_proof" and degraded < 3:
            score["final_correctness"] = 0.0
            score["weighted_score"] = round(
                100 * (0.35 * score["requirements_coverage"] + 0.35 * score["key_steps_hit_rate"]), 2
            )
            degraded += 1
    candidate["summary"]["category_pass_rates"]["advanced_proof"] = 57.14

    gates = load_gates(str(ROOT / "gates.yaml"))
    verdict = compare_v2_reports(baseline, candidate, gates)
    assert verdict["status"] == "rejected"
    assert any("advanced_proof" in failure for failure in verdict["failures"])


def test_compare_v2_approves_identical_reports(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    gates = load_gates(str(ROOT / "gates.yaml"))
    verdict = compare_v2_reports(baseline, json.loads(json.dumps(baseline)), gates)
    assert verdict["status"] == "approved"
    assert verdict["failures"] == []


def test_compare_v2_rejects_dataset_hash_mismatch(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = run_mocked_v2(bundle, run_id="cand", label="cand")
    candidate["dataset_hash"] = "0" * 64
    gates = load_gates(str(ROOT / "gates.yaml"))
    with pytest.raises(ValueError):
        compare_v2_reports(baseline, candidate, gates)
