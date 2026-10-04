import asyncio

import pytest

from app.services.answer_critic import AnswerCritic, CriticReport


def test_off_mode_makes_zero_reviews():
    critic = AnswerCritic(mode="off")
    assert critic.should_review("run-1") is False
    assert asyncio.run(critic.review(run_id="run-1", question="q", final_answer="完整回答")) is None


def test_all_mode_uses_deterministic_mock_and_reports_pass_or_warn():
    critic = AnswerCritic(mode="all")
    report = asyncio.run(critic.review(run_id="run-all", question="求极限", final_answer="这是一个足够完整的数学回答。"))
    assert report is not None
    assert report.verdict == "pass"
    assert report.token_cost == 0
    assert report.model == "deterministic-mock"


def test_sample_mode_is_stable_and_respects_zero_rate():
    critic = AnswerCritic(mode="sample", sample_rate=0)
    assert critic.should_review("same-run") is False
    assert critic.should_review("same-run") is False


def test_critic_failure_does_not_escape_to_main_path():
    async def failing(**_kwargs):
        raise RuntimeError("critic unavailable")

    critic = AnswerCritic(mode="all", evaluator=failing)
    assert asyncio.run(critic.review(run_id="run-fail", question="q", final_answer="回答")) is None
