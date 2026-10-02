import json


import pytest


class _Agent:
    _last_run_metadata = {}
    _follow_up_text = None

    async def stream(self, *args, **kwargs):
        yield {"__agent_event__": True, "event_type": "thinking", "message": "正在分析问题并选择合适的工具"}
        yield {"__agent_event__": True, "event_type": "tool_start", "tool": "math_solver", "message": "正在调用 math_solver"}
        yield "最终答案：1"


@pytest.mark.asyncio
async def test_stream_handler_emits_safe_agent_step_events_before_content():
    from app.services.stream_handler import stream_agent_response

    chunks = [
        chunk
        async for chunk in stream_agent_response(
            _Agent(), "1+0", "session-a", user_id="user-a"
        )
    ]
    assert any(chunk.startswith("event: agent_step") for chunk in chunks)
    step_chunk = next(chunk for chunk in chunks if chunk.startswith("event: agent_step"))
    payload = json.loads(step_chunk.split("data: ", 1)[1].strip())
    assert payload["event_type"] == "thinking"
    assert "__agent_event__" not in payload
    content_chunks = [chunk for chunk in chunks if '"type": "content"' in chunk]
    assert content_chunks
    assert any(json.loads(chunk.split("data: ", 1)[1].strip())["content"] == "最终答案：1" for chunk in content_chunks)
    assert any('"type": "done"' in chunk for chunk in chunks)
