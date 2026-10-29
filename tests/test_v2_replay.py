import pytest

from model_quality_eval.dataset import load_v2_dataset
from model_quality_eval.v2_replay import build_v2_replay_plan


@pytest.fixture(scope="module")
def bundle():
    return load_v2_dataset("evaluations/model_quality/v2")


def test_all_v2_cases_have_deterministic_synthetic_replay_plans(bundle):
    plans = [
        build_v2_replay_plan(case, dataset_hash=bundle.computed_hash, run_id="synthetic-run")
        for case in bundle.cases
    ]
    assert len(plans) == 108
    assert len({plan["current_session"]["owner_id"] for plan in plans}) == 108
    assert sum(bool(plan["image_asset"]) for plan in plans) == 10
    assert sum(plan["retrieval_fixture_present"] for plan in plans) == 14
    assert sum(bool(plan["tool_failure"]) for plan in plans) == 12


def test_same_external_session_id_stays_owned_by_distinct_users(bundle):
    case = bundle.by_id["mq-v2-multi-turn-022"]
    plan = build_v2_replay_plan(case, dataset_hash=bundle.computed_hash, run_id="synthetic-run")
    current = plan["current_session"]
    protected = plan["protected_session"]
    assert current["external_session_id"] == protected["external_session_id"]
    assert current["owner_id"] != protected["owner_id"]
    assert protected["messages"][0]["content"] == "y²=9"
    assert all("y²=9" not in message["content"] for message in current["messages"])


def test_interrupted_draft_is_not_replayed_as_committed_history(bundle):
    case = bundle.by_id["mq-v2-multi-turn-021"]
    plan = build_v2_replay_plan(case, dataset_hash=bundle.computed_hash, run_id="synthetic-run")
    assert plan["interrupted_draft"] == "h(x)=x⁴"
    assert all("x⁴" not in message["content"] for message in plan["current_session"]["messages"])


def test_replay_preserves_long_history_order_and_checkpoint_text(bundle):
    case = bundle.by_id["mq-v2-multi-turn-024"]
    plan = build_v2_replay_plan(case, dataset_hash=bundle.computed_hash, run_id="synthetic-run")
    assert len(plan["current_session"]["messages"]) == 42
    assert plan["current_session"]["messages"][0]["content"] == "原题：求 1+1。"
    assert "999" in plan["checkpoint_summary"]
