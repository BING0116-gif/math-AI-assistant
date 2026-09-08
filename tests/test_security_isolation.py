from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from agent_core.agent import MathAgent
from app.api import agent_api


def _agent_without_initialization() -> MathAgent:
    agent = object.__new__(MathAgent)
    agent._session_histories = {}
    return agent


def test_session_isolation():
    agent = _agent_without_initialization()
    history_a = agent._get_session_history("user-a", "default")
    history_b = agent._get_session_history("user-b", "default")

    history_a.add_user_message("secret-a")
    history_b.add_user_message("secret-b")

    assert history_a is not history_b
    assert set(agent._session_histories) == {"user-a:default", "user-b:default"}
    assert "secret-b" not in str(history_a.messages)
    assert "secret-a" not in str(history_b.messages)


@pytest.mark.asyncio
async def test_thought_ownership(monkeypatch):
    process = SimpleNamespace(to_dict=lambda: {"owner": "user-a"})

    class Recorder:
        def get_session_processes(self, key, limit=None):
            return [process] if key == "user-a:shared" else []

    class FakeAgent:
        session_key = staticmethod(MathAgent.session_key)

        def get_thought_recorder(self):
            return Recorder()

    monkeypatch.setattr(agent_api, "get_agent", lambda: FakeAgent())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/agent/thought/shared",
        "headers": [],
        "state": {"user_id": "user-b"},
    }
    with pytest.raises(HTTPException) as exc:
        await agent_api.get_thought_history("shared", Request(scope))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_branches_forward_user_id():
    from app.services.stream_handler import (
        stream_agent_response,
        stream_recognize_response,
        stream_multimodal_response,
    )

    calls = []

    class FakeAgent:
        async def stream(self, message, session_id=None, user_id=None, **kwargs):
            calls.append(("stream", session_id, user_id))
            yield "ok"

    async for _ in stream_agent_response(
        FakeAgent(), "hello", "default", user_id="user-a"
    ):
        pass
    async for _ in stream_multimodal_response(
        FakeAgent(), "hello", None, "default", user_id="user-a"
    ):
        pass
    async for _ in stream_recognize_response(
        FakeAgent(), "aGVsbG8=", "default", user_id="user-a"
    ):
        pass

    assert calls == [
        ("stream", "default", "user-a"),
        ("stream", "default", "user-a"),
        ("stream", "default", "user-a"),
    ]
