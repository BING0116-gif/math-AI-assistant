import json
from pathlib import Path
import subprocess
import sys

import pytest

from model_quality_eval.dataset import load_dataset
from model_quality_eval.guards import EvaluationSafetyError, side_effect_delta, validate_eval_database_url
from model_quality_eval.runner import (
    answer_text_chunk,
    ai_enabled_from_environment,
    deterministic_session_id,
    estimated_cost_from_environment,
    accumulated_tokens,
    live_timeout_seconds_from_environment,
    live_token_budget_from_environment,
    live_budget_from_environment,
    load_live_checkpoint,
    run_live,
    run_live_sync,
    run_mocked,
    summarise_stability,
)


def test_live_answer_capture_ignores_agent_events():
    assert answer_text_chunk({"__agent_event__": True, "event_type": "thinking", "message": "内部步骤"}) == ""
    assert answer_text_chunk("最终答案：2") == "最终答案：2"
from model_quality_eval.schema import CaseResult


DATASET = Path("evaluations/model_quality/v1")


def test_eval_database_guard_accepts_only_separate_postgresql_test_targets():
    value = "postgresql://user:secret@localhost/math_ai_eval"
    assert validate_eval_database_url(value, "postgresql://user:secret@localhost/math_ai") == value
    with pytest.raises(EvaluationSafetyError, match="PostgreSQL"):
        validate_eval_database_url("sqlite:///data/math_ai_test.db")
    with pytest.raises(EvaluationSafetyError, match="_eval or _test"):
        validate_eval_database_url("postgresql://localhost/math_ai")
    with pytest.raises(EvaluationSafetyError, match="must not equal"):
        validate_eval_database_url(value, value)
    with pytest.raises(EvaluationSafetyError, match="must not equal"):
        validate_eval_database_url(value, "postgresql://other:credentials@localhost/math_ai_eval")


def test_session_keys_are_idempotent_and_case_scoped():
    first = deterministic_session_id("a" * 64, "run-1", "mq-text-001", 1)
    assert first == deterministic_session_id("a" * 64, "run-1", "mq-text-001", 1)
    assert first != deterministic_session_id("a" * 64, "run-1", "mq-text-002", 1)
    assert first != deterministic_session_id("a" * 64, "run-1", "mq-text-001", 2)


def test_side_effect_delta_is_explicit_for_audited_tables():
    delta = side_effect_delta({"chat_messages": 1, "practice_attempts": 2}, {"chat_messages": 3, "practice_attempts": 2})
    assert delta["chat_messages"] == 2
    assert delta["practice_attempts"] == 0
    updated = side_effect_delta(
        {"user_profiles": {"count": 1, "digest": "before"}},
        {"user_profiles": {"count": 1, "digest": "after"}},
    )
    assert updated["user_profiles"] == 1


def test_cost_is_calculated_only_from_explicit_reviewed_rates(monkeypatch):
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 500_000, "total_tokens": 1_500_000}
    monkeypatch.delenv("EVAL_INPUT_COST_PER_MILLION", raising=False)
    monkeypatch.delenv("EVAL_OUTPUT_COST_PER_MILLION", raising=False)
    assert estimated_cost_from_environment(usage) is None
    monkeypatch.setenv("EVAL_INPUT_COST_PER_MILLION", "2")
    monkeypatch.setenv("EVAL_OUTPUT_COST_PER_MILLION", "6")
    assert estimated_cost_from_environment(usage) == 5.0


def test_live_budget_requires_a_positive_explicit_value(monkeypatch):
    monkeypatch.delenv("EVAL_MAX_COST_USD", raising=False)
    assert live_budget_from_environment() is None
    monkeypatch.setenv("EVAL_MAX_COST_USD", "0")
    assert live_budget_from_environment() is None
    monkeypatch.setenv("EVAL_MAX_COST_USD", "2.00")
    assert live_budget_from_environment() == 2.0


def test_live_token_and_timeout_budgets_are_explicit_and_positive(monkeypatch):
    monkeypatch.delenv("EVAL_MAX_TOKENS", raising=False)
    monkeypatch.delenv("EVAL_TIMEOUT_SECONDS", raising=False)
    assert live_token_budget_from_environment() is None
    assert live_timeout_seconds_from_environment() is None
    monkeypatch.setenv("EVAL_MAX_TOKENS", "1200")
    monkeypatch.setenv("EVAL_TIMEOUT_SECONDS", "30")
    assert live_token_budget_from_environment() == 1200
    assert live_timeout_seconds_from_environment() == 30.0


def test_accumulated_tokens_fails_closed_when_telemetry_is_missing():
    assert accumulated_tokens([], [{"execution": {"token_usage": None}}]) is None


def test_mocked_run_covers_all_cases_without_network_or_hard_failures(monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    bundle = load_dataset(DATASET)
    report = run_mocked(bundle, run_id="mock-run", label="offline")
    assert report["status"] == "mocked_pass"
    assert report["summary"]["case_count"] == 60
    assert report["summary"]["hard_failure_count"] == 0
    assert report["model"] == "deterministic-mock"
    assert report["full_dataset"] is True
    assert report["schema_version"] == "1.0"
    assert len(report["schema_hash"]) == 64
    assert len(report["case_hashes"]) == 60
    assert report["environment"]["python"]


def test_evaluator_never_imports_a_vendor_model_client():
    forbidden = ("AsyncOpenAI(", "ChatOpenAI(", "openai import", "dashscope import")
    for path in Path("model_quality_eval").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(marker in source for marker in forbidden), path


def test_live_ai_gate_requires_deepseek_llm_api_key_not_dashscope(monkeypatch):
    # 评测复用应用主模型（DeepSeek），因此启用门槛是 LLM_API_KEY，而非千问 DASHSCOPE_API_KEY。
    from app.config.settings import settings

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    assert ai_enabled_from_environment() is False

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test-deepseek")
    assert ai_enabled_from_environment() is True

    monkeypatch.setenv("AI_ENABLED", "false")
    assert ai_enabled_from_environment() is False


def test_live_run_is_not_run_when_ai_is_disabled_and_never_requires_a_database(monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_DATABASE_URL", raising=False)
    bundle = load_dataset(DATASET)
    report = run_live_sync(bundle, run_id="live-disabled", label="candidate", selected=bundle.cases[:1])
    assert report["status"] == "not_run"
    assert report["reason"] == "AI_UNAVAILABLE"
    assert report["summary"]["case_count"] == 0


@pytest.mark.asyncio
async def test_live_stops_after_stability_retry_without_cost_telemetry(monkeypatch, tmp_path):
    import model_quality_eval.runner as runner
    import app.data.database as database

    bundle = load_dataset(DATASET)
    cases = bundle.cases[:2]
    primary = CaseResult.model_validate(
        run_mocked(bundle, run_id="telemetry-stop", label="offline", selected=cases[:1])["results"][0]
    )
    calls = []

    async def no_op():
        return None

    async def seed(_run_id):
        return {"user_a": "eval-a", "user_b": "eval-b"}

    async def fake_case(_bundle, case, _run_id, _fixtures, attempt=1):
        calls.append((case.case_id, attempt))
        execution = primary.execution.model_copy(update={
            "attempt": attempt,
            "token_usage": None if attempt == 2 else {"total_tokens": 100},
            "estimated_cost": None if attempt == 2 else 0.01,
        })
        return primary.model_copy(update={"execution": execution, "weighted_score": 0.0})

    monkeypatch.setattr(runner, "ai_enabled_from_environment", lambda: True)
    monkeypatch.setattr(runner, "live_budget_from_environment", lambda: 1.0)
    monkeypatch.setattr(runner, "live_token_budget_from_environment", lambda: 10000)
    monkeypatch.setattr(runner, "live_timeout_seconds_from_environment", lambda: 5.0)
    monkeypatch.setattr(runner, "_seed_live_fixtures", seed)
    monkeypatch.setattr(runner, "run_live_case", fake_case)
    monkeypatch.setattr(database, "init_db", no_op)
    monkeypatch.setattr(database, "close_db", no_op)
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql://localhost/model_quality_eval")
    report = await run_live(
        bundle, run_id="telemetry-stop", label="live", selected=cases,
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert calls == [(cases[0].case_id, 1), (cases[0].case_id, 2)]
    assert report["status"] == "incomplete"
    assert report["reason"] == "EVAL_TELEMETRY_MISSING"
    assert len(report["stability_runs"]) == 1


def test_cli_resumes_a_completed_case_set_without_reexecution(tmp_path):
    output = tmp_path / "idempotent-run"
    arguments = [
        "run", "--dataset", str(DATASET), "--mode", "mocked", "--run-id", "fixed-run",
        "--label", "offline", "--case-id", "mq-text-001", "--output", str(output),
    ]
    command = [sys.executable, "-m", "scripts.model_quality_eval", *arguments]
    first = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(first.stdout.strip())
    second = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(second.stdout.strip())
    assert first_payload["run_id"] == second_payload["run_id"] == "fixed-run"
    assert second_payload["resumed"] is True


def test_live_checkpoint_restores_only_matching_completed_attempts(tmp_path):
    bundle = load_dataset(DATASET)
    case = bundle.cases[0]
    result = run_mocked(bundle, run_id="checkpoint", label="offline", selected=[case])["results"][0]
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "checkpoint_schema_version": "1.0",
                "run_id": "checkpoint",
                "dataset_hash": bundle.computed_hash,
                "selected_case_ids": [case.case_id],
                "results": [result],
                "stability_runs": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    restored, stability = load_live_checkpoint(
        checkpoint, bundle=bundle, run_id="checkpoint", cases=[case]
    )
    assert [item.case_id for item in restored] == [case.case_id]
    assert stability == []
    with pytest.raises(RuntimeError, match="does not match"):
        load_live_checkpoint(checkpoint, bundle=bundle, run_id="different", cases=[case])


def test_stability_summary_reports_variation_without_replacing_primary_result():
    bundle = load_dataset(DATASET)
    case = bundle.cases[0]
    primary = run_mocked(bundle, run_id="stability", label="offline", selected=[case])["results"][0]
    repeated = json.loads(json.dumps(primary))
    repeated["execution"]["attempt"] = 2
    repeated["execution"]["response"] = "另一种表达"
    repeated["weighted_score"] = 75.0
    summary = summarise_stability(
        [CaseResult.model_validate(primary)],
        [repeated],
    )
    assert summary[0]["score_min"] == 75.0
    assert summary[0]["score_max"] == 100.0
    assert summary[0]["unique_response_count"] == 2
