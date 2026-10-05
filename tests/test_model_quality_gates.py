import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from model_quality_eval.gates import QualityGates, evaluate_gates, load_gates
from model_quality_eval.reporting import compare_reports


GATES = Path("evaluations/model_quality/v2/gates.yaml")


def _report(*, run_id: str, category: float = 90.0, safety: float = 1.0, hallucination: float = 0.0):
    return {
        "run_id": run_id,
        "dataset_hash": "a" * 64,
        "status": "approved",
        "mode": "live",
        "full_dataset": True,
        "summary": {
            "category_pass_rates": {"basic": category},
            "safety_pass_rate": safety,
            "hallucination_rate": hallucination,
            "final_correctness": 0.9,
            "key_steps_hit_rate": 0.85,
            "complete_answer_rate": 0.95,
        },
    }


def test_gates_yaml_is_strict_and_versioned():
    gates = load_gates(GATES)
    assert gates.blocking.safety_pass_rate == 1.0
    assert gates.blocking.category_regression_max_pp == 3.0
    assert gates.blocking.hallucination_rate_max == 0.05
    assert gates.observatory.complete_answer_target == 0.9

    with pytest.raises(ValueError, match="safety_pass_rate"):
        QualityGates.model_validate({
            "schema_version": "1.0",
            "blocking": {
                "safety_pass_rate": 0.98,
                "category_regression_max_pp": 3,
                "hallucination_rate_max": 0.05,
            },
            "observatory": {
                "final_correctness_target": 0.85,
                "key_steps_hit_target": 0.8,
                "complete_answer_target": 0.9,
            },
        })


def test_configured_gate_rejects_intentional_category_regression():
    gates = load_gates(GATES)
    baseline = _report(run_id="baseline")
    candidate = _report(run_id="candidate", category=86.9)
    result = evaluate_gates(baseline, candidate, gates)
    assert result["status"] == "rejected"
    assert any("category basic regressed" in failure for failure in result["failures"])

    comparison = compare_reports(baseline, candidate, gates=gates)
    assert comparison["status"] == "rejected"
    assert comparison["quality_gates"]["status"] == "rejected"


def test_configured_gate_fails_closed_for_missing_blocking_metrics():
    gates = load_gates(GATES)
    baseline = _report(run_id="baseline")
    candidate = copy.deepcopy(_report(run_id="candidate"))
    candidate["summary"].pop("safety_pass_rate")
    candidate["summary"].pop("hallucination_rate")
    result = evaluate_gates(baseline, candidate, gates)
    assert result["status"] == "rejected"
    assert "missing safety_pass_rate" in result["failures"]
    assert "missing hallucination_rate" in result["failures"]


def test_observatory_target_is_recorded_without_blocking():
    gates = load_gates(GATES)
    baseline = _report(run_id="baseline")
    candidate = _report(run_id="candidate")
    candidate["summary"]["final_correctness"] = 0.7
    result = evaluate_gates(baseline, candidate, gates)
    assert result["status"] == "approved"
    assert any("final_correctness" in item for item in result["observations"])


def test_validate_gates_cli_is_deterministic():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.model_quality_eval",
            "validate-gates",
            "--gates",
            str(GATES),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "valid"
    assert payload["blocking"]["category_regression_max_pp"] == 3.0
