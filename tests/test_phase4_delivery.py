import asyncio
import pytest

from app.services.model_gateway import ModelGateway
from app.adapters.question_system.remote_impl import RemoteQuestionSystemAdapter


@pytest.mark.asyncio
async def test_model_gateway_retries_and_records_usage():
    calls = 0
    class Response:
        model = "fixture-model"
        usage = {"prompt_tokens": 10, "completion_tokens": 5}
    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return Response()
    result = await ModelGateway(max_retries=1).call(operation, provider="fixture")
    assert calls == 2
    assert result.request_id and result.input_tokens == 10 and result.output_tokens == 5
    assert result.fallback_reason is None


@pytest.mark.asyncio
async def test_model_gateway_fallback_is_explicit():
    async def operation(): raise ValueError("provider unavailable")
    async def fallback(error): return {"source": "rule_fallback", "error": type(error).__name__}
    result = await ModelGateway(max_retries=0, timeout_seconds=0.1).call(operation, provider="remote", fallback=fallback)
    assert result.provider == "fallback"
    assert result.fallback_reason == "ValueError"
    assert "fallback" in (result.quality_flags or [])


def test_remote_question_response_schema_rejects_empty_payload():
    with pytest.raises(ValueError):
        RemoteQuestionSystemAdapter._question({}, "q1")


def test_remote_question_response_schema_normalizes_contract():
    value = RemoteQuestionSystemAdapter._question({"id": "remote-1", "difficulty": "4", "knowledge_points": None}, "q1")
    assert value["id"] == "remote-1"
    assert value["difficulty"] == 4
    assert value["knowledge_points"] == []
