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

    asyncio.run(scenario())
