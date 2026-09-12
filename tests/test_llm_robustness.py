"""LLM 跨厂商响应容错回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_service import (
    JSON_PARTIAL_NOTICE,
    TRUNCATION_NOTICE,
    LLMProvider,
    LLMResponseValidationError,
    LLMService,
)


@pytest.fixture
def service():
    svc = LLMService.__new__(LLMService)
    svc.api_key = "test-key"
    svc.api_base = "https://test.api/v1"
    svc.model = "deepseek-v4-flash"
    svc.math_model = "deepseek-v4-flash"
    svc.temperature = 0.2
    svc.max_tokens = 512
    svc.provider = LLMProvider.DEEPSEEK
    svc._cache = {}
    svc._cache_ttl = 300
    svc._cache_max_size = 100
    svc._initialized = True
    svc._client = MagicMock()
    return svc


def _response(content, *, finish_reason="stop", tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None, model="deepseek-v4-flash")


@pytest.mark.asyncio
async def test_empty_tool_call_is_rejected_without_retry(service, caplog):
    empty_call = SimpleNamespace(function=SimpleNamespace(name="", arguments=""))
    service._client.chat.completions.create = AsyncMock(
        return_value=_response("", finish_reason="tool_calls", tool_calls=[empty_call])
    )

    with pytest.raises(LLMResponseValidationError, match="空工具调用"):
        await service.generate("请调用工具", use_cache=False)

    assert service._client.chat.completions.create.await_count == 1
    assert "拒绝空工具调用" in caplog.text


@pytest.mark.asyncio
async def test_truncated_json_retry_stays_partial_after_diagnostic_repair(service, caplog):
    service._client.chat.completions.create = AsyncMock(
        side_effect=[
            _response('{"answer": {"value": 42', finish_reason="length"),
            _response('{"answer": {"value": 42'),
        ]
    )

    result = await service.generate_json("只返回 JSON")

    assert service._client.chat.completions.create.await_count == 2
    assert result.partial is True
    assert result.parsed_json == {"answer": {"value": 42}}
    assert result.parse_error
    assert JSON_PARTIAL_NOTICE in result.content
    assert "已标记 partial" in caplog.text


@pytest.mark.asyncio
async def test_invalid_json_retries_once_then_returns_visible_partial_error(service):
    service._client.chat.completions.create = AsyncMock(
        side_effect=[_response("not-json"), _response("still-not-json")]
    )

    result = await service.generate_json("只返回 JSON")

    assert service._client.chat.completions.create.await_count == 2
    assert result.partial is True
    assert result.parsed_json is None
    assert result.parse_error
    assert "JSON 不完整" in result.content


@pytest.mark.asyncio
async def test_finish_reason_length_marks_partial_and_warns_user(service, caplog):
    service._client.chat.completions.create = AsyncMock(
        return_value=_response("尚未完成的回答", finish_reason="length")
    )

    result = await service.generate("解题", use_cache=True)

    assert result.partial is True
    assert result.finish_reason == "length"
    assert TRUNCATION_NOTICE in result.content
    assert service._cache == {}
    assert "回答被截断" in caplog.text


@pytest.mark.asyncio
async def test_stream_finish_reason_length_yields_visible_notice(service, caplog):
    async def stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="前半段"), finish_reason=None)]
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="length")]
        )

    service._client.chat.completions.create = AsyncMock(return_value=stream())

    chunks = [chunk async for chunk in service.generate_stream("解题")]

    assert chunks == ["前半段", TRUNCATION_NOTICE]
    assert "流式回答被截断" in caplog.text


@pytest.mark.asyncio
async def test_json_retry_can_recover_with_a_complete_second_response(service):
    service._client.chat.completions.create = AsyncMock(
        side_effect=[_response('{"answer":'), _response('{"answer": 42}')]
    )

    result = await service.generate_json("只返回 JSON")

    assert result.partial is False
    assert result.parsed_json == {"answer": 42}
    assert result.parse_error is None
