import asyncio
from types import SimpleNamespace

from agent_core.strategies import langchain_react as strategy_module


def test_agent_registers_max_iterations_middleware(monkeypatch):
    converter = SimpleNamespace(convert_batch=lambda tools: [])
    monkeypatch.setattr(strategy_module, "get_tool_converter", lambda: converter)
    monkeypatch.setattr(strategy_module, "filter_tools_for_mode", lambda tools, mode: [])
    monkeypatch.setattr(strategy_module, "create_agent", lambda **kwargs: kwargs)

    strategy = strategy_module.LangChainReActStrategy(
        llm=object(),
        registry=SimpleNamespace(get_all_tools=lambda: []),
        system_prompt="test",
        max_iterations=3,
    )

    agent = strategy._ensure_agent_initialized()

    assert len(agent["middleware"]) == 1
    assert isinstance(agent["middleware"][0], strategy_module.MaxIterationsMiddleware)
    assert agent["middleware"][0]._max_iterations == 3


def test_agent_stream_returns_timeout_message_when_event_stream_hangs(monkeypatch):
    async def hanging_events(*args, **kwargs):
        await asyncio.sleep(0.05)
        yield {"event": "on_chat_model_stream", "data": {}}

    async def scenario():
        strategy = strategy_module.LangChainReActStrategy(
            llm=object(),
            registry=SimpleNamespace(get_all_tools=lambda: []),
            system_prompt="test",
            timeout_seconds=0.001,
        )
        monkeypatch.setattr(
            strategy,
            "_ensure_agent_initialized",
            lambda mode, capability_allowed_tools: SimpleNamespace(
                astream_events=hanging_events
            ),
        )

        chunks = [
            chunk
            async for chunk in strategy.stream(
                "请计算极限",
                "session-timeout",
                {"user_id": "user-timeout", "tutor_mode": "tutor_free"},
            )
        ]
        assert any("执行超时" in chunk for chunk in chunks)
        assert strategy._last_run_status == "timeout"

    asyncio.run(scenario())


def test_agent_budget_defaults_resolve_from_settings(monkeypatch):
    values = {
        "AGENT_MAX_TOOL_ROUNDS": 7,
        "AGENT_TOTAL_TIMEOUT_SECONDS": 33.0,
        "AGENT_MAX_TOTAL_TOKENS": 1234,
    }
    monkeypatch.setattr(strategy_module, "_budget_setting", lambda name, fallback: values[name])

    strategy = strategy_module.LangChainReActStrategy(
        llm=object(),
        registry=SimpleNamespace(get_all_tools=lambda: []),
        system_prompt="test",
    )

    assert strategy._max_iterations == 7
    assert strategy._timeout_seconds == 33.0
    assert strategy._token_budget == 1234


def test_agent_stream_stops_gracefully_on_token_budget(monkeypatch):
    closed = {"aclose_called": False}

    async def over_budget_events(*args, **kwargs):
        try:
            usage = SimpleNamespace(usage_metadata={"total_tokens": 999_999})
            yield {"event": "on_chat_model_end", "data": {"output": usage}}
            yield {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="预算触顶后的内容")}}
        finally:
            closed["aclose_called"] = True

    async def scenario():
        strategy = strategy_module.LangChainReActStrategy(
            llm=object(),
            registry=SimpleNamespace(get_all_tools=lambda: []),
            system_prompt="test",
            max_total_tokens=1000,
        )
        monkeypatch.setattr(
            strategy,
            "_ensure_agent_initialized",
            lambda mode, capability_allowed_tools: SimpleNamespace(
                astream_events=over_budget_events
            ),
        )

        chunks = [
            chunk
            async for chunk in strategy.stream(
                "请证明",
                "session-budget",
                {"user_id": "user-budget", "tutor_mode": "tutor_free"},
            )
        ]

        assert any("长度上限" in chunk for chunk in chunks)
        # 触顶后的模型事件不得再被消费
        assert not any("预算触顶后的内容" in chunk for chunk in chunks)
        assert strategy._last_run_status == "budget_exceeded"
        # break 后必须确定性关闭底层事件流，不留挂起的 LLM 连接
        assert closed["aclose_called"] is True

    asyncio.run(scenario())
