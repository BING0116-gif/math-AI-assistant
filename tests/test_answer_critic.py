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


def test_latex_imbalance_is_caught_deterministically():
    critic = AnswerCritic(mode="all")
    report = asyncio.run(
        critic.review(run_id="run-latex", question="q", final_answer="这是一个足够完整的数学回答，含 $\\frac{a}{b$ 未闭合公式。")
    )
    assert report is not None
    assert report.verdict == "warn"
    assert any(issue.code == "latex_wellformed" for issue in report.issues)


class _FakeLLM:
    def __init__(self, content, tokens=123):
        self._content = content
        self._tokens = tokens
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        from types import SimpleNamespace

        return SimpleNamespace(
            content=self._content,
            usage_metadata={"total_tokens": self._tokens},
        )


def _llm_critic(monkeypatch, content, tokens=123):
    import datetime

    import app.services.answer_critic as critic_module

    monkeypatch.setattr("app.config.settings.settings.CRITIC_MODEL", "critic-test-model")
    monkeypatch.setattr("app.config.settings.settings.LLM_API_KEY", "sk-test")
    critic_module._DAILY_TOKENS.update({"date": datetime.date.today().isoformat(), "used": 0})
    return AnswerCritic(mode="all", llm=_FakeLLM(content, tokens))


def test_real_model_verdict_merges_with_deterministic(monkeypatch):
    payload = '{"verdict":"fail","issues":[{"code":"no_gap","detail":"缺少取等条件","location":"第3步"}],"checked_by":["answered_question","no_gap"]}'
    critic = _llm_critic(monkeypatch, payload)
    report = asyncio.run(
        critic.review(run_id="run-llm", question="证明 f''(xi)>=8", final_answer="这是一个足够完整的数学回答。")
    )
    assert report is not None
    # LLM 判 fail 与确定性 pass 合并取最严
    assert report.verdict == "fail"
    assert any(issue.code == "no_gap" for issue in report.issues)
    assert report.checked_by and "no_gap" in report.checked_by and "latex_wellformed" in report.checked_by
    assert report.token_cost == 123


def test_real_model_malformed_json_degrades_to_none(monkeypatch):
    critic = _llm_critic(monkeypatch, "我认为这段回答很好，但不是 JSON。")
    report = asyncio.run(
        critic.review(run_id="run-bad", question="q", final_answer="这是一个足够完整的数学回答。")
    )
    assert report is None  # 观察性失败,不影响主回答


def test_daily_token_cap_disables_critic(monkeypatch):
    import datetime

    import app.services.answer_critic as critic_module

    monkeypatch.setattr("app.config.settings.settings.CRITIC_MODEL", "critic-test-model")
    monkeypatch.setattr("app.config.settings.settings.LLM_API_KEY", "sk-test")
    critic_module._DAILY_TOKENS.update({"date": datetime.date.today().isoformat(), "used": 500_000})
    try:
        critic = AnswerCritic(mode="all", llm=_FakeLLM("{}"))
        # 限额触顶:should_review 直接 False,不发 LLM 调用
        assert critic.should_review("run-cap") is False
        assert asyncio.run(critic.review(run_id="run-cap", question="q", final_answer="回答")) is None
    finally:
        critic_module._DAILY_TOKENS.update({"used": 0})


def test_deterministic_mock_never_builds_llm():
    critic = AnswerCritic(mode="all")
    assert critic._uses_llm is False
    report = asyncio.run(
        critic.review(run_id="run-mock", question="q", final_answer="这是一个足够完整的数学回答。")
    )
    assert report is not None and report.token_cost == 0
