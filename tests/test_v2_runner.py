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
    preflight_live_v2,
    run_mocked_v2,
)

ROOT = Path(__file__).parents[1] / "evaluations" / "model_quality" / "v2"


@pytest.fixture(scope="module")
def bundle():
    return load_v2_dataset(str(ROOT))


def test_mocked_run_full_dataset_pipeline_selfcheck(bundle):
    """全量案例:oracle 确定性应答必须全满分(管线自检),耗时应远低于 5 分钟预算。"""
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


def test_v2_exact_answer_does_not_match_inside_a_different_number(bundle):
    from model_quality_eval.v2_scoring import score_v2_case

    by_id = {case.id: case for case in bundle.cases}
    assert score_v2_case(by_id["mq-v2-multi-turn-016"], "最终答案：10").final_correctness == 0
    assert score_v2_case(by_id["mq-v2-multi-turn-014"], "最终答案：x=20").final_correctness == 0
    assert score_v2_case(by_id["mq-v2-multi-turn-014"], "最终答案：x=2").final_correctness == 1
    variant_case = by_id["mq-v2-multi-turn-014"].model_copy(update={"allowed_answer_variants": ["x=+2"]})
    assert score_v2_case(variant_case, "最终答案：x=+2").final_correctness == 1


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
    assert len(verdict["failure_case_ids"]) == 3
    assert all(verdict["case_score_deltas"][case_id] < 0 for case_id in verdict["failure_case_ids"])


def test_compare_v2_marks_identical_mocked_reports_as_pipeline_pass(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    gates = load_gates(str(ROOT / "gates.yaml"))
    verdict = compare_v2_reports(baseline, json.loads(json.dumps(baseline)), gates)
    assert verdict["status"] == "pipeline_pass"
    assert verdict["failures"] == []
    assert verdict["model_quality_claim"] is False


def test_compare_v2_rejects_dataset_hash_mismatch(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = run_mocked_v2(bundle, run_id="cand", label="cand")
    candidate["dataset_hash"] = "0" * 64
    gates = load_gates(str(ROOT / "gates.yaml"))
    with pytest.raises(ValueError):
        compare_v2_reports(baseline, candidate, gates)


def test_compare_v2_does_not_approve_unreviewed_live_reports(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = json.loads(json.dumps(baseline))
    for report in (baseline, candidate):
        report["mode"] = "live"
        report["status"] = "needs_human_review"
    verdict = compare_v2_reports(baseline, candidate, load_gates(str(ROOT / "gates.yaml")))
    assert verdict["status"] == "incomplete"
    assert verdict["model_quality_claim"] is False
    assert "LIVE_REVIEW_OR_BASELINE_MISSING" in verdict["failures"]


def test_compare_v2_rejects_mixed_mock_and_live(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = json.loads(json.dumps(baseline))
    candidate["mode"] = "live"
    verdict = compare_v2_reports(baseline, candidate, load_gates(str(ROOT / "gates.yaml")))
    assert verdict["status"] == "incomplete"
    assert "REPORT_MODES_NOT_COMPARABLE" in verdict["failures"]


def test_compare_v2_live_fails_closed_on_cost_and_latency_regressions(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = json.loads(json.dumps(baseline))
    baseline.update(mode="live", status="approved")
    candidate.update(mode="live", status="baseline_only")
    for report in (baseline, candidate):
        report["summary"]["latency"] = {"p95_ms": 100}
        report["summary"]["cost"] = {"average": 0.01}
    candidate["summary"]["latency"]["p95_ms"] = 125
    candidate["summary"]["cost"]["average"] = 0.012
    verdict = compare_v2_reports(baseline, candidate, load_gates(str(ROOT / "gates.yaml")))
    assert verdict["status"] == "rejected"
    assert "REGRESSION:latency.p95_ms" in verdict["failures"]
    assert "REGRESSION:cost.average" in verdict["failures"]


def test_compare_v2_live_rejects_missing_case_score(bundle):
    baseline = run_mocked_v2(bundle, run_id="base", label="base")
    candidate = json.loads(json.dumps(baseline))
    baseline.update(mode="live", status="approved")
    candidate.update(mode="live", status="baseline_only")
    for report in (baseline, candidate):
        report["summary"]["latency"] = {"p95_ms": 100}
        report["summary"]["cost"] = {"average": 0.01}
    missing_id = candidate["scores"].pop()["case_id"]
    verdict = compare_v2_reports(baseline, candidate, load_gates(str(ROOT / "gates.yaml")))
    assert verdict["status"] == "incomplete"
    assert verdict["missing_score_case_ids"] == [missing_id]


def test_v2_live_preflight_fails_closed_without_credentials_or_review(bundle, monkeypatch):
    for name in (
        "AI_ENABLED", "LLM_API_KEY", "EVAL_DATABASE_URL", "EVAL_MAX_COST_USD",
        "EVAL_MAX_TOKENS", "EVAL_TIMEOUT_SECONDS", "EVAL_INPUT_COST_PER_MILLION",
        "EVAL_OUTPUT_COST_PER_MILLION",
    ):
        monkeypatch.delenv(name, raising=False)
    result = preflight_live_v2(bundle)
    assert result["status"] == "incomplete"
    assert result["model_calls"] == 0
    assert "GOLD_REVIEW_PENDING" in result["issues"]
    assert "EVAL_DATABASE_UNSAFE" in result["issues"]
    assert len(result["draft_case_ids"]) == 13


def test_v2_live_preflight_rejects_production_database(bundle, monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/school_eval")
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql://localhost/school_eval")
    monkeypatch.setenv("EVAL_MAX_COST_USD", "2")
    monkeypatch.setenv("EVAL_MAX_TOKENS", "1000")
    monkeypatch.setenv("EVAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("EVAL_INPUT_COST_PER_MILLION", "1")
    monkeypatch.setenv("EVAL_OUTPUT_COST_PER_MILLION", "2")
    result = preflight_live_v2(bundle, selected=[bundle.cases[0]])
    assert result["issues"] == ["EVAL_DATABASE_UNSAFE"]
    assert result["model_calls"] == 0


def test_v2_live_preflight_rejects_database_from_app_settings(bundle, monkeypatch):
    from app.config.settings import settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql://localhost/school_eval")
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/school_eval")
    result = preflight_live_v2(bundle, selected=[bundle.cases[0]])
    assert "EVAL_DATABASE_UNSAFE" in result["issues"]


def test_v2_live_preflight_checks_independent_eval_target(bundle, monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/school")
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql://localhost/school_eval")
    monkeypatch.setenv("EVAL_MAX_COST_USD", "2")
    monkeypatch.setenv("EVAL_MAX_TOKENS", "1000")
    monkeypatch.setenv("EVAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("EVAL_INPUT_COST_PER_MILLION", "1")
    monkeypatch.setenv("EVAL_OUTPUT_COST_PER_MILLION", "2")
    result = preflight_live_v2(bundle, selected=[bundle.cases[0]])
    assert result["status"] == "ready_for_live_implementation"
    assert result["issues"] == []
    assert result["model_calls"] == 0
