"""Deterministic contract checks for the agent replay matrix."""

from pathlib import Path

import yaml


REPLAY = Path(__file__).parents[1] / "evaluations" / "agent_replay" / "v1" / "cases.yaml"


def test_agent_replay_matrix_covers_planning_quality_boundaries():
    payload = yaml.safe_load(REPLAY.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) >= 10
    ids = {case["case_id"] for case in cases}
    assert len(ids) == len(cases)
    actions = {case["expected_action"] for case in cases}
    assert {"diagnostic_entry", "review_recommendation", "solve_with_verification"} <= actions
    assert {"honest_degradation", "empty_state_without_fallback", "request_clarification"} <= actions


def test_agent_replay_cases_forbid_cross_user_and_fabricated_facts():
    payload = yaml.safe_load(REPLAY.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        forbidden = set(case.get("forbidden", []))
        assert "use_other_user_data" in forbidden or "use_user_b_error_book" in forbidden
        assert "fabricate_mastery" in forbidden or any(
            item.startswith("fabricate_") or item.startswith("claim_") for item in forbidden
        )
