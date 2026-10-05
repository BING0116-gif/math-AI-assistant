import asyncio

from tools.base_tool import ToolOutput
from tools.execution_guard import GuardPolicy, ToolExecutionGuard


def test_guard_normalizes_timeout_and_does_not_retry_non_idempotent_call():
    calls = 0

    async def hanging():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return ToolOutput(success=True, result="late")

    async def scenario():
        guard = ToolExecutionGuard(GuardPolicy(timeout_s=0.001, retries=2, circuit_enabled=False))
        result = await guard.run("write_tool", hanging, retryable=False)
        assert result.success is False
        assert result.metadata["error_code"] == "TOOL_TIMEOUT"
        assert calls == 1

    asyncio.run(scenario())


def test_guard_retries_read_tool_then_returns_success():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return ToolOutput(success=True, result="ok")

    async def scenario():
        guard = ToolExecutionGuard(GuardPolicy(retries=1, retry_backoff_s=0, circuit_enabled=False))
        result = await guard.run("read_tool", flaky, retryable=True)
        assert result.success is True
        assert calls == 2

    asyncio.run(scenario())


def test_guard_opens_circuit_after_consecutive_failures():
    calls = 0

    async def failing():
        nonlocal calls
        calls += 1
        raise RuntimeError("downstream")

    async def scenario():
        guard = ToolExecutionGuard(
            GuardPolicy(retries=0, circuit_enabled=True, failure_threshold=2, cooldown_s=60)
        )
        first = await guard.run("search_tool", failing)
        second = await guard.run("search_tool", failing)
        third = await guard.run("search_tool", failing)
        assert first.metadata["error_code"] == "TOOL_ERROR"
        assert second.metadata["error_code"] == "TOOL_ERROR"
        assert third.metadata["error_code"] == "TOOL_UNAVAILABLE"
        assert calls == 2

    asyncio.run(scenario())
