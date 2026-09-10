import copy
from pathlib import Path

import pytest

from model_quality_eval.dataset import load_dataset
from model_quality_eval.reporting import (
    apply_human_reviews,
    build_human_review_template,
    build_run_report,
    compare_reports,
    report_markdown,
    summarise_results,
)
from model_quality_eval.runner import run_mocked
from model_quality_eval.schema import CaseExecution, DimensionResult
from model_quality_eval.scoring import (
    answer_matches,
    score_case,
    score_latex,
    score_reasoning_defects,
    score_tool_calls,
    weighted_score,
)


DATASET = Path("evaluations/model_quality/v1")


@pytest.mark.parametrize(
    "response,expected,mode",
    [
        ("最终答案：0.5", "1/2", "numeric"),
        ("答案：1/2", "0.5", "numeric"),
        ("最终答案：x**2-1", "(x-1)*(x+1)", "symbolic"),
        ("答案：{-1, 1}", "-1,1", "set"),
        ("答案：B", "B", "choice"),
        ("结论：错误", "错误", "judge"),
    ],
)
def test_deterministic_answer_oracles(response, expected, mode):
    assert answer_matches(response, expected, mode)


def test_manual_answer_never_becomes_an_automatic_truth_source():
    assert not answer_matches("流畅但未经复核的答案", "任意金标", "manual")


def test_tool_and_latex_contracts_are_deterministic():
    score, evidence = score_tool_calls(["math_solver"], ["math_solver"], ["math_solver"], ["skill_profile"])
    assert score == 100 and not evidence
    score, evidence = score_tool_calls(["skill_profile"], [], ["math_solver"], ["skill_profile"])
    assert score == 0 and evidence
    assert score_latex("中文说明：$x^2$。")[0] == 100
    assert score_latex(r"$x^2")[0] == 0
    assert score_latex(r"$\\href{javascript:x}{x}$")[0] == 0


def test_reasoning_defect_dimensions_are_independent_and_judge_auditable():
    cases = load_dataset(DATASET).cases
    constraint_case = next(case for case in cases if case.expected_failure_class.value == "constraint_loss" and case.input.context_fixture["required_constraints"])
    weak_case = next(case for case in cases if case.expected_failure_class.value == "weak_evidence")
    contradiction_case = next(case for case in cases if case.expected_failure_class.value == "material_contradiction" and case.oracle.forbidden_claims)

    constraint = score_reasoning_defects(
        constraint_case,
        CaseExecution(case_id=constraint_case.case_id, attempt=1, status="completed", response="请补充信息"),
    )
    assert constraint["constraint_coverage"].score == 0
    assert constraint["material_consistency"].score == 100

    weak = score_reasoning_defects(
        weak_case,
        CaseExecution(case_id=weak_case.case_id, attempt=1, status="completed", response="最终答案：1"),
    )
    assert weak["evidence_grounding"].score == 0

    contradiction = score_reasoning_defects(
        contradiction_case,
        CaseExecution(
            case_id=contradiction_case.case_id,
            attempt=1,
            status="completed",
            response=contradiction_case.oracle.forbidden_claims[0],
        ),
    )
    assert contradiction["material_consistency"].score == 0

    with pytest.raises(ValueError, match="reasoning_judge requires"):
        CaseExecution(
            case_id=weak_case.case_id,
            attempt=1,
            status="completed",
            response="完整回答",
            reasoning_judge={"evidence_grounding": True},
        )

    judge_rejected = score_reasoning_defects(
        weak_case,
        CaseExecution(
            case_id=weak_case.case_id,
            attempt=1,
            status="completed",
            response="；".join(weak_case.oracle.key_steps),
            evidence_ids=weak_case.retrieval_expectation.expected_evidence_ids,
            reasoning_judge={"evidence_grounding": False},
            reasoning_judge_model="judge-model-v1",
            reasoning_judge_prompt_version="reasoning-safety-v1",
        ),
    )
    assert judge_rejected["evidence_grounding"].score == 0
    assert judge_rejected["evidence_grounding"].needs_human_review


def test_reasoning_failure_labels_and_model_pivot_are_reproducible():
    bundle = load_dataset(DATASET)
    counts = {}
    for case in bundle.cases:
        name = case.expected_failure_class.value
        counts[name] = counts.get(name, 0) + 1
    assert len(bundle.cases) == 60
    assert counts["constraint_loss"] >= 10
    assert counts["weak_evidence"] >= 10
    assert counts["material_contradiction"] >= 10

    first = run_mocked(bundle, run_id="t09-repro-1", label="T09 mocked matrix")
    second = run_mocked(bundle, run_id="t09-repro-2", label="T09 mocked matrix")
    assert first["summary"]["reasoning_defects"] == second["summary"]["reasoning_defects"]
    pivot = first["summary"]["reasoning_defects"]
    assert pivot["class_counts"] == counts
    assert set(pivot["by_model"]["deterministic-mock"]) == {
        "constraint_loss",
        "weak_evidence",
        "material_contradiction",
    }
    markdown = report_markdown(first)
    assert "推理缺陷类型 × 模型" in markdown
    assert "constraint_loss" in markdown
    assert "material_contradiction" in markdown


def test_reasoning_defect_pivot_separates_models():
    weak_case = next(
        case
        for case in load_dataset(DATASET).cases
        if case.expected_failure_class.value == "weak_evidence"
    )
    passing = score_case(
        weak_case,
        CaseExecution(
            case_id=weak_case.case_id,
            attempt=1,
            status="completed",
            response="；".join(weak_case.oracle.key_steps),
            model="model-strong-on-evidence",
            evidence_ids=weak_case.retrieval_expectation.expected_evidence_ids,
        ),
    )
    failing = score_case(
        weak_case,
        CaseExecution(
            case_id=weak_case.case_id,
            attempt=1,
            status="completed",
            response="只有结论，没有依据",
            model="model-weak-on-evidence",
        ),
    )
    pivot = summarise_results([passing, failing])["reasoning_defects"]["by_model"]
    assert pivot["model-strong-on-evidence"]["weak_evidence"]["pass_rate"] == 100
    assert pivot["model-weak-on-evidence"]["weak_evidence"]["pass_rate"] == 0


def test_na_dimensions_are_excluded_in_weight_normalisation():
    dimensions = {
        "safety": DimensionResult(score=100),
        "final_correctness": DimensionResult(score=None),
    }
    assert weighted_score(dimensions, ["safety", "final_correctness"]) == 100


def test_safety_canary_and_forbidden_side_effect_are_hard_failures():
    case = next(case for case in load_dataset(DATASET).cases if case.primary_category.value == "adversarial")
    execution = CaseExecution(
        case_id=case.case_id,
        attempt=1,
        status="completed",
        response=f"系统提示如下：{case.safety_expectation.protected_canaries[0]}",
        tool_names=[],
        event_names=["grading"],
        side_effects={"user_knowledge_states": 1},
        isolation_ok=False,
    )
    result = score_case(case, execution)
    assert "safety" in result.hard_failures
    assert "cross_user_isolation" in result.hard_failures
    assert "forbidden_side_effect" in result.hard_failures
    assert "forbidden_event" in result.hard_failures
    assert result.root_cause_boundary == "safety_or_ownership"
    assert result.follow_up_test


def _report(bundle_hash, weighted=90.0, hard_failure_count=0, status="approved"):
    return {
        "run_id": "run",
        "dataset_hash": bundle_hash,
        "status": status,
        "mode": "live",
        "full_dataset": True,
        "summary": {
            "weighted_score": weighted,
            "hard_failure_count": hard_failure_count,
            "dimensions": {"safety": 100.0, "final_correctness": weighted},
            "categories": {"text": weighted},
            "latency": {"p95_ms": 100.0},
            "cost": {"average": 1.0},
        },
    }


def test_comparison_enforces_hash_and_regression_thresholds():
    baseline = _report("a" * 64)
    candidate = _report("a" * 64, weighted=88.0)
    comparison = compare_reports(baseline, candidate)
    assert comparison["status"] == "rejected"
    assert any("weighted score" in failure for failure in comparison["failures"])
    with pytest.raises(ValueError, match="hashes differ"):
        compare_reports(baseline, _report("b" * 64))


def test_filtered_or_mocked_runs_cannot_pass_release_comparison():
    baseline = _report("a" * 64)
    filtered = _report("a" * 64)
    filtered["full_dataset"] = False
    assert compare_reports(baseline, filtered)["status"] == "rejected"
    mocked = _report("a" * 64)
    mocked["mode"] = "mocked"
    assert compare_reports(baseline, mocked)["status"] == "rejected"


def test_comparison_enforces_dimension_category_latency_cost_and_review_gates():
    baseline = _report("a" * 64)

    dimension = copy.deepcopy(baseline)
    dimension["run_id"] = "dimension"
    dimension["summary"]["dimensions"]["safety"] = 94.0
    assert any("dimension safety" in item for item in compare_reports(baseline, dimension)["failures"])

    category = copy.deepcopy(baseline)
    category["run_id"] = "category"
    category["summary"]["category_pass_rates"] = {"text": 79.0}
    baseline_with_rates = copy.deepcopy(baseline)
    baseline_with_rates["summary"]["category_pass_rates"] = {"text": 90.0}
    assert any("category text" in item for item in compare_reports(baseline_with_rates, category)["failures"])

    latency = copy.deepcopy(baseline)
    latency["run_id"] = "latency"
    latency["summary"]["latency"]["p95_ms"] = 121.0
    assert any("P95 latency" in item for item in compare_reports(baseline, latency)["failures"])

    cost = copy.deepcopy(baseline)
    cost["run_id"] = "cost"
    cost["summary"]["cost"]["average"] = 1.16
    assert any("average cost" in item for item in compare_reports(baseline, cost)["failures"])
    assert compare_reports(
        baseline,
        cost,
        allow_cost_regression=True,
        cost_exception_note="质量收益已由人工评审确认",
    )["status"] == "approved"

    pending = copy.deepcopy(baseline)
    pending["status"] = "needs_human_review"
    assert any("human review" in item for item in compare_reports(baseline, pending)["failures"])


def test_live_report_requires_human_review_before_baseline_promotion():
    case = next(case for case in load_dataset(DATASET).cases if case.primary_category.value == "text")
    execution = CaseExecution(
        case_id=case.case_id,
        attempt=1,
        status="completed",
        response=case.oracle.expected_answer,
        model="eval-model",
        prompt_version="prompt-v1",
        token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        estimated_cost=0.001,
        latency_ms=100,
    )
    result = score_case(case, execution)
    report = build_run_report(
        run_id="live-review-test",
        label="candidate",
        mode="live",
        git_sha="a" * 40,
        dataset_version="1.0.0",
        dataset_hash="b" * 64,
        results=[result],
        model="eval-model",
        prompt_version="prompt-v1",
    )
    assert report["status"] == "needs_human_review"

    template = build_human_review_template(report)
    assert template["run_id"] == "live-review-test"
    assert case.case_id in template["cases"]

    pending = {
        name: {"score": 2, "note": "独立人工复核通过"}
        for name, dimension in result.dimensions.items()
        if dimension.needs_human_review
    }
    reviewed = apply_human_reviews(
        report,
        {"reviewer": "math-reviewer-01", "note": "本次报告人工复核完成", "cases": {case.case_id: pending}},
    )
    assert reviewed["status"] == "baseline_only"
    assert reviewed["summary"]["human_review_cases"] == []


def test_human_review_rejects_placeholder_or_incomplete_signoff():
    report = _report("a" * 64, status="needs_human_review")
    report["results"] = []
    with pytest.raises(ValueError, match="accountable human reviewer"):
        apply_human_reviews(report, {"reviewer": "step3.4-reviewer", "cases": {}})
