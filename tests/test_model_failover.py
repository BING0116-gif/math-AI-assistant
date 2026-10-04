"""阶段二 4.4 分级降级与备用模型 failover 回归测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from agent_core import degradation as degradation_module
from agent_core import model_failover as failover_module
from agent_core.model_failover import ModelFailoverCoordinator
from agent_core.strategies import langchain_react as strategy_module


def make_coordinator(**overrides) -> ModelFailoverCoordinator:
    defaults = dict(
        enabled=True,
        candidates=["deepseek-v4-flash"],
        window_seconds=60.0,
        failure_threshold=3,
        probe_seconds=300.0,
    )
    defaults.update(overrides)
    return ModelFailoverCoordinator(**defaults)


def test_disabled_by_default_returns_primary_and_never_switches():
    coordinator = ModelFailoverCoordinator(enabled=False, candidates=["deepseek-v4-flash"], clock=lambda: 0.0)
    assert coordinator.enabled is False
    assert coordinator.current_model("deepseek-chat") == "deepseek-chat"
    assert coordinator.record_failure("deepseek-chat") is None


def test_window_failures_trigger_sticky_switch():
    clock = {"t": 0.0}
    coordinator = make_coordinator(clock=lambda: clock["t"])

    assert coordinator.record_failure("deepseek-chat") is None
    clock["t"] += 10
    assert coordinator.record_failure("deepseek-chat") is None
    clock["t"] += 10
    assert coordinator.record_failure("deepseek-chat") == "deepseek-v4-flash"
    # 粘性：后续 run 直接使用候选，无需再次达阈值
    assert coordinator.current_model("deepseek-chat") == "deepseek-v4-flash"


def test_failures_outside_window_do_not_accumulate():
    clock = {"t": 0.0}
    coordinator = make_coordinator(clock=lambda: clock["t"])

    assert coordinator.record_failure("deepseek-chat") is None
    clock["t"] += 120  # 超出 60s 窗口
    assert coordinator.record_failure("deepseek-chat") is None
    clock["t"] += 10
    assert coordinator.record_failure("deepseek-chat") is None


def test_success_clears_window_but_keeps_sticky_model():
    clock = {"t": 0.0}
    coordinator = make_coordinator(clock=lambda: clock["t"])

    for _ in range(3):
        coordinator.record_failure("deepseek-chat")
    assert coordinator.current_model("deepseek-chat") == "deepseek-v4-flash"

    coordinator.record_success()
    assert coordinator.current_model("deepseek-chat") == "deepseek-v4-flash"


def test_probe_period_returns_to_primary():
    clock = {"t": 0.0}
    coordinator = make_coordinator(clock=lambda: clock["t"])

    for _ in range(3):
        coordinator.record_failure("deepseek-chat")
    clock["t"] += 301  # 探测期（300s）结束
    assert coordinator.current_model("deepseek-chat") == "deepseek-chat"


def test_ineligible_candidates_are_skipped_fail_closed(monkeypatch):
    monkeypatch.setattr(failover_module, "MODEL_CAPABILITIES", {"deepseek-chat": {"tool_call": True, "vision": False}})
    # 候选未登记能力表 → 不可参与切换
    coordinator = make_coordinator(candidates=["unknown-model"], clock=lambda: 0.0)
    for _ in range(3):
        assert coordinator.record_failure("deepseek-chat") is None
    assert coordinator.current_model("deepseek-chat") == "deepseek-chat"


def test_candidate_exhaustion_returns_none(monkeypatch):
    monkeypatch.setattr(failover_module, "MODEL_CAPABILITIES", {"b": {"tool_call": True}, "c": {"tool_call": True}})
    clock = {"t": 0.0}
    coordinator = make_coordinator(candidates=["b", "c"], clock=lambda: clock["t"])

    assert coordinator.record_failure("a", frozenset({"tool_call"})) is None
    assert coordinator.record_failure("a", frozenset({"tool_call"})) is None
    clock["t"] += 5
    assert coordinator.record_failure("a", frozenset({"tool_call"})) == "b"
    clock["t"] += 5
    # 粘性期内不重复切换
    assert coordinator.record_failure("a", frozenset({"tool_call"})) is None
    clock["t"] += 301  # 探测期结束回到主模型，再次连续失败 → 下一个候选 c
    for _ in range(3):
        switched = coordinator.record_failure("a", frozenset({"tool_call"}))
        clock["t"] += 5
        if switched:
            break
    assert switched == "c"
    clock["t"] += 301
    for _ in range(3):
        switched = coordinator.record_failure("a", frozenset({"tool_call"}))
        clock["t"] += 5
        if switched:
            break
    assert switched is None  # 候选耗尽 → 调用方走 L4


def test_degradation_templates_are_honest_and_available():
    text = degradation_module.degradation_text("model_failure")
    assert "服务暂不可用" in text
    assert "不会丢失上下文" in text
    assert degradation_module.degradation_text("unknown-key")  # 兜底文案永远非空


def test_degradation_loader_falls_back_when_yaml_missing(monkeypatch):
    monkeypatch.setattr(degradation_module, "_CACHE", None)
    original_read = __import__("pathlib").Path.read_text

    def broken_read(self, *args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(__import__("pathlib").Path, "read_text", broken_read)
    text = degradation_module.degradation_text("timeout")
    assert "执行超时" in text
    monkeypatch.setattr(__import__("pathlib").Path, "read_text", original_read)
    monkeypatch.setattr(degradation_module, "_CACHE", None)


def test_strategy_uses_l4_template_and_status_on_llm_failure(monkeypatch):
    async def failing_events(*args, **kwargs):
        raise RuntimeError("connection reset")
        yield  # pragma: no cover

    async def scenario():
        strategy = strategy_module.LangChainReActStrategy(
            llm=object(),
            registry=SimpleNamespace(get_all_tools=lambda: []),
            system_prompt="test",
        )
        monkeypatch.setattr(
            strategy,
            "_ensure_agent_initialized",
            lambda mode, capability_allowed_tools: SimpleNamespace(astream_events=failing_events),
        )
        monkeypatch.setattr(strategy_module, "get_model_failover_coordinator", lambda: SimpleNamespace(
            current_model=lambda primary, required_capabilities=frozenset({"tool_call"}): primary,
            record_failure=lambda primary, required_capabilities=frozenset({"tool_call"}): None,
            record_success=lambda: None,
        ))

        chunks = [
            chunk
            async for chunk in strategy.stream(
                "请证明",
                "session-l4",
                {"user_id": "user-l4", "tutor_mode": "tutor_free"},
            )
        ]
        assert any("服务暂不可用" in chunk for chunk in chunks)
        assert strategy._last_run_status == "failed_l4"

    asyncio.run(scenario())


def test_strategy_rebinds_llm_for_sticky_failover_run(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    calls = {"success": 0}

    async def ok_events(*args, **kwargs):
        yield {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="候选模型回答")}}

    async def scenario():
        strategy = strategy_module.LangChainReActStrategy(
            llm=SimpleNamespace(model_name="deepseek-chat", temperature=0.5),
            registry=SimpleNamespace(get_all_tools=lambda: []),
            system_prompt="test",
        )
        sticky = SimpleNamespace(
            current_model=lambda primary, required_capabilities=frozenset({"tool_call"}): "deepseek-v4-flash",
            record_failure=lambda primary, required_capabilities=frozenset({"tool_call"}): None,
            record_success=lambda: calls.__setitem__("success", calls["success"] + 1),
        )
        monkeypatch.setattr(strategy_module, "get_model_failover_coordinator", lambda: sticky)
        monkeypatch.setattr(
            strategy,
            "_ensure_agent_initialized",
            lambda mode, capability_allowed_tools: SimpleNamespace(astream_events=ok_events),
        )

        chunks = [
            chunk
            async for chunk in strategy.stream(
                "请证明",
                "session-degraded",
                {"user_id": "user-degraded", "tutor_mode": "tutor_free"},
            )
        ]

        assert any("候选模型回答" in chunk for chunk in chunks)
        assert strategy._llm.model_name == "deepseek-v4-flash"
        assert strategy._last_run_status == "degraded"
        assert calls["success"] == 1

    asyncio.run(scenario())
