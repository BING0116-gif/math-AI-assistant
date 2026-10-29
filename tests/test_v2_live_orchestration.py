import pytest

from model_quality_eval.dataset import load_v2_dataset
from model_quality_eval.guards import AUDITED_TABLES
from model_quality_eval.v2_live import compare_abc_reports, run_v2_with_executor
from model_quality_eval.v2_runner import mock_response_v2


def clean_effects():
    return {table: 0 for table in AUDITED_TABLES}


def config(mode="A", **extra):
    return {
        "mode": mode, "isolation_id": f"eval-{mode}",
        "shadow_enabled": mode in {"B", "C"}, "injection_enabled": mode == "C",
        "model": "synthetic-model", "prompt_version": "synthetic-prompt",
        **extra,
    }


@pytest.fixture
def bundle():
    return load_v2_dataset("evaluations/model_quality/v2")


@pytest.mark.asyncio
async def test_v2_checkpoint_resumes_only_same_configuration(bundle, tmp_path):
    cases = bundle.cases[:2]
    calls = []

    async def executor(case, plan, configuration):
        calls.append(case.id)
        assert plan["case_id"] == case.id
        assert plan["current_session"]["owner_id"].startswith("mq-v2-")
        return {
            "response": mock_response_v2(case), "token_usage": {"total_tokens": 10},
            "estimated_cost": 0.01, "model": "synthetic-model",
            "prompt_version": "synthetic-prompt", "latency_ms": 1,
            "isolation_ok": True, "side_effects": clean_effects(),
        }

    args = dict(
        bundle=bundle, run_id="run-a", label="A", configuration=config(model="synthetic-model"),
        executor=executor, max_cost_usd=1, max_tokens=100, timeout_seconds=1,
        checkpoint_path=tmp_path / "checkpoint.json", selected=cases,
    )
    first = await run_v2_with_executor(**args)
    assert first["status"] == "needs_human_review"
    assert len(calls) == 2
    again = await run_v2_with_executor(**args)
    assert again["scores"] == first["scores"]
    assert len(calls) == 2
    with pytest.raises(ValueError, match="identity mismatch"):
        await run_v2_with_executor(**{**args, "configuration": config("B", model="synthetic-model")})
    with pytest.raises(ValueError, match="identity mismatch"):
        await run_v2_with_executor(**{**args, "max_cost_usd": 2})


@pytest.mark.asyncio
async def test_v2_missing_telemetry_stops_without_false_quality_result(bundle):
    async def executor(case, plan, configuration):
        return {"response": mock_response_v2(case), "model": "synthetic-model"}

    report = await run_v2_with_executor(
        bundle, run_id="run-b", label="A", configuration=config(), executor=executor,
        max_cost_usd=1, max_tokens=100, timeout_seconds=1, selected=bundle.cases[:2],
    )
    assert report["status"] == "incomplete"
    assert report["reason"] == "EVAL_TELEMETRY_MISSING"
    assert report["scores"] == []


@pytest.mark.asyncio
async def test_v2_budget_stops_before_next_case(bundle):
    calls = []

    async def executor(case, plan, configuration):
        calls.append(case.id)
        return {
            "response": mock_response_v2(case), "token_usage": {"total_tokens": 10},
            "estimated_cost": 0.5, "model": "synthetic-model",
            "prompt_version": "synthetic-prompt", "latency_ms": 1,
            "isolation_ok": True, "side_effects": clean_effects(),
        }

    report = await run_v2_with_executor(
        bundle, run_id="run-c", label="A", configuration=config(), executor=executor,
        max_cost_usd=0.5, max_tokens=100, timeout_seconds=1, selected=bundle.cases[:2],
    )
    assert report["status"] == "incomplete"
    assert report["reason"] == "EVAL_BUDGET_REACHED"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_v2_live_orchestration_rejects_draft_cases(bundle):
    async def executor(case, plan, configuration):
        raise AssertionError("draft must never reach executor")

    with pytest.raises(ValueError, match="draft gold"):
        await run_v2_with_executor(
            bundle, run_id="run-d", label="A",
            configuration=config(), executor=executor,
            max_cost_usd=1, max_tokens=100, timeout_seconds=1,
            selected=[bundle.by_id["mq-v2-multi-turn-024"]],
        )


def test_abc_reports_require_same_model_and_independent_state():
    reports = {
        mode: {
            "mode": "live", "status": "needs_human_review",
            "dataset_hash": "hash", "selected_case_ids": ["case-1"],
            "configuration": {
                **config(mode, model="synthetic-model", temperature=0),
            },
        }
        for mode in "ABC"
    }
    assert compare_abc_reports(reports)["status"] == "comparable"
    reports["B"]["configuration"]["isolation_id"] = "eval-A"
    reports["C"]["configuration"]["temperature"] = 0.5
    verdict = compare_abc_reports(reports)
    assert verdict["status"] == "incomplete"
    assert set(verdict["failures"]) == {"ISOLATION_NOT_INDEPENDENT", "MODEL_CONFIGURATION_MISMATCH"}
    reports["B"]["configuration"]["shadow_enabled"] = False
    assert "CHECKPOINT_FLAGS_MISMATCH" in compare_abc_reports(reports)["failures"]


@pytest.mark.asyncio
async def test_v2_orchestration_rejects_wrong_mode_flags(bundle):
    async def executor(case, plan, configuration):
        raise AssertionError("invalid mode must never call executor")

    with pytest.raises(ValueError, match="checkpoint flags"):
        await run_v2_with_executor(
            bundle, run_id="flags", label="C",
            configuration=config("C", injection_enabled=False), executor=executor,
            max_cost_usd=1, max_tokens=100, timeout_seconds=1, selected=bundle.cases[:1],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("isolation_ok", "changed_table", "expected_failure"),
    [(False, None, "USER_ISOLATION_FAILED"), (True, "learning_records", "UNEXPECTED_SIDE_EFFECT:learning_records")],
)
async def test_v2_safety_failure_is_hard_stop(bundle, tmp_path, isolation_ok, changed_table, expected_failure):
    calls = []

    async def executor(case, plan, configuration):
        calls.append(case.id)
        effects = clean_effects()
        if changed_table:
            effects[changed_table] = 1
        return {
            "response": mock_response_v2(case), "token_usage": {"total_tokens": 10},
            "estimated_cost": 0.01, "model": "synthetic-model",
            "prompt_version": "synthetic-prompt", "latency_ms": 1,
            "isolation_ok": isolation_ok, "side_effects": effects,
        }

    args = dict(
        bundle=bundle, run_id="safety", label="A", configuration=config(),
        executor=executor, max_cost_usd=1, max_tokens=100, timeout_seconds=1,
        selected=bundle.cases[:2], checkpoint_path=tmp_path / "safety.json",
    )
    report = await run_v2_with_executor(**args)
    assert report["status"] == "rejected"
    assert report["reason"] == "EVAL_SAFETY_FAILURE"
    assert report["summary"]["safety_pass_rate"] == 0
    assert expected_failure in report["records"][0]["safety_failures"]
    assert len(calls) == 1
    resumed = await run_v2_with_executor(**args)
    assert resumed["status"] == "rejected"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_v2_missing_isolation_evidence_stops_before_scoring(bundle, tmp_path):
    calls = []
    async def executor(case, plan, configuration):
        calls.append(case.id)
        return {
            "response": mock_response_v2(case), "token_usage": {"total_tokens": 10},
            "estimated_cost": 0.01, "model": "synthetic-model",
            "prompt_version": "synthetic-prompt", "latency_ms": 1,
        }

    args = dict(
        bundle=bundle, run_id="missing", label="A", configuration=config(),
        executor=executor, max_cost_usd=1, max_tokens=100, timeout_seconds=1,
        selected=bundle.cases[:1], checkpoint_path=tmp_path / "missing.json",
    )
    report = await run_v2_with_executor(**args)
    assert report["status"] == "incomplete"
    assert report["reason"] == "EVAL_ISOLATION_EVIDENCE_MISSING"
    assert report["scores"] == []
    assert (await run_v2_with_executor(**args))["reason"] == "EVAL_ISOLATION_EVIDENCE_MISSING"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_v2_executor_failure_is_terminal_on_resume(bundle, tmp_path):
    calls = []

    async def executor(case, plan, configuration):
        calls.append(case.id)
        raise RuntimeError("synthetic executor failure")

    args = dict(
        bundle=bundle, run_id="failure", label="A", configuration=config(),
        executor=executor, max_cost_usd=1, max_tokens=100, timeout_seconds=1,
        selected=bundle.cases[:1], checkpoint_path=tmp_path / "failure.json",
    )
    first = await run_v2_with_executor(**args)
    second = await run_v2_with_executor(**args)
    assert first["status"] == second["status"] == "incomplete"
    assert first["reason"] == second["reason"] == "EVAL_EXECUTOR_FAILED"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_v2_malformed_tool_trace_is_terminal(bundle, tmp_path):
    calls = []

    async def executor(case, plan, configuration):
        calls.append(case.id)
        return {
            "response": mock_response_v2(case), "token_usage": {"total_tokens": 10},
            "estimated_cost": 0.01, "model": "synthetic-model",
            "prompt_version": "synthetic-prompt", "latency_ms": 1,
            "isolation_ok": True, "side_effects": clean_effects(),
            "tool_trace": [{"tool": None}],
        }

    args = dict(
        bundle=bundle, run_id="bad-trace", label="A", configuration=config(),
        executor=executor, max_cost_usd=1, max_tokens=100, timeout_seconds=1,
        selected=bundle.cases[:1], checkpoint_path=tmp_path / "bad-trace.json",
    )
    assert (await run_v2_with_executor(**args))["reason"] == "EVAL_SCORING_FAILED"
    assert (await run_v2_with_executor(**args))["reason"] == "EVAL_SCORING_FAILED"
    assert len(calls) == 1

