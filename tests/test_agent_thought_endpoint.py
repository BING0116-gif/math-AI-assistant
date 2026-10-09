"""GET /api/agent/thought/{session_id} 的会话归属与思考纪要。

旧实现取的是 "default" 记录器，而真实 run 的记录器按 "{user_id}:{session_id}"
建立，所以这个端点恒 404。这里把契约钉住：本人会话 200、他人会话 404、
未认证 401，并且能按需取回该会话最近一轮的有界纪要。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from agent_core.agent import MathAgent
from agent_core.strategies.langchain_react import LangChainReActStrategy
from app.api import agent_api


_SAMPLE_TRACE = [
    {
        "round": 1,
        "kind": "process",
        "text": "我先取几个点，再调用绘图工具。",
        "elapsed_ms": 812.5,
        "truncated": False,
        "tools": [
            {
                "tool": "math_visualize",
                "label": "函数图像绘制",
                "status": "success",
                "code": "",
                "elapsed_ms": 210.5,
                "input_summary": "type=function_plot, points=3",
                "output_summary": "status=ok",
            }
        ],
    }
]


def _strategy():
    return LangChainReActStrategy(
        llm=object(),
        registry=SimpleNamespace(get_all_tools=lambda: []),
        system_prompt="test",
        timeout_seconds=5,
    )


class _FakeAgent:
    """只带会话委托逻辑的 Agent 桩：get_thought_recorder/get_session_trace 用真实现。"""

    session_key = staticmethod(MathAgent.session_key)
    get_thought_recorder = MathAgent.get_thought_recorder
    get_session_trace = MathAgent.get_session_trace

    def __init__(self, strategy):
        self._strategy = strategy


def _request(user_id):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/agent/thought/chat-1",
            "headers": [],
            "state": {"user_id": user_id},
        }
    )


@pytest.fixture()
def wired(monkeypatch):
    """一次真实形状的 run：会话记录器里有过程记录，策略缓存里有纪要。"""
    monkeypatch.setattr(agent_api, "is_ai_available", lambda: True)
    strategy = _strategy()
    agent = _FakeAgent(strategy)
    monkeypatch.setattr(agent_api, "get_agent", lambda: agent)
    key = agent.session_key("user-a", "chat-1")

    recorder = strategy.get_thought_recorder(key)
    recorder.start_process("画出 y=x^2 的图像")
    recorder.finish_process("图像已生成")
    strategy.cache_session_trace(key, _SAMPLE_TRACE)
    return agent, key


@pytest.mark.asyncio
async def test_owner_gets_processes_and_trace(wired):
    _, key = wired

    payload = await agent_api.get_thought_history("chat-1", _request("user-a"))

    assert payload["session_id"] == "chat-1"
    assert payload["total"] == 1
    assert payload["processes"][0]["session_id"] == key
    # 纪要走同一份 public_trace 结构，供"展开全文"按需拉取
    assert payload["trace"] == _SAMPLE_TRACE


@pytest.mark.asyncio
async def test_other_users_session_is_not_found(wired):
    """会话键由已认证的 user_id 构成：拿别人的 session_id 读不到任何东西。"""
    with pytest.raises(HTTPException) as exc:
        await agent_api.get_thought_history("chat-1", _request("user-b"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(wired):
    with pytest.raises(HTTPException) as exc:
        await agent_api.get_thought_history("chat-1", _request(None))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_session_still_returns_404(monkeypatch):
    monkeypatch.setattr(agent_api, "is_ai_available", lambda: True)
    strategy = _strategy()
    agent = _FakeAgent(strategy)
    monkeypatch.setattr(agent_api, "get_agent", lambda: agent)

    with pytest.raises(HTTPException) as exc:
        await agent_api.get_thought_history("never-used", _request("user-a"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_legacy_recorder_without_session_argument_still_works(monkeypatch):
    """旧式记录器不接受会话键：退回全局记录器但仍按会话键过滤，不拿别人的会话。"""
    monkeypatch.setattr(agent_api, "is_ai_available", lambda: True)
    process = SimpleNamespace(to_dict=lambda: {"session_id": "user-a:chat-1"})

    class LegacyAgent:
        session_key = staticmethod(MathAgent.session_key)

        def get_thought_recorder(self, *args):
            if args:
                raise TypeError("takes 1 positional argument but 2 were given")
            return SimpleNamespace(
                get_session_processes=lambda key, limit=None: [process] if key == "user-a:chat-1" else []
            )

    monkeypatch.setattr(agent_api, "get_agent", lambda: LegacyAgent())

    payload = await agent_api.get_thought_history("chat-1", _request("user-a"))

    assert payload["total"] == 1
    assert payload["trace"] == []


def test_recorder_lookup_is_per_session_not_default():
    """回归根因：默认记录器与真实 run 的记录器不是同一个对象。"""
    strategy = _strategy()
    agent = _FakeAgent(strategy)

    assert agent.get_thought_recorder() is strategy.thought_recorder
    scoped = agent.get_thought_recorder("user-a:chat-1")
    assert scoped is not strategy.thought_recorder
    assert scoped.session_id == "user-a:chat-1"
    # 同一会话键复用同一个记录器，历史才不会散落在多个对象里
    assert agent.get_thought_recorder("user-a:chat-1") is scoped


def test_trace_cache_is_bounded_and_user_scoped():
    strategy = _strategy()

    for index in range(25):
        strategy.cache_session_trace(f"user-a:chat-{index}", _SAMPLE_TRACE)
    assert len(strategy._trace_cache) <= strategy._trace_cache_sessions
    # 最近写入的会话一定还在
    assert strategy.get_session_trace("user-a:chat-24") == _SAMPLE_TRACE

    strategy.cache_session_trace("user-b:chat-1", _SAMPLE_TRACE)
    strategy.clear_user_data("user-b")
    assert strategy.get_session_trace("user-b:chat-1") == []


def test_cache_session_trace_tolerates_strategies_without_support():
    """非 LangChain 策略没有缓存能力时不能抛错，纪要仍靠消息 metadata 回看。"""
    agent = object.__new__(MathAgent)
    agent._strategy = SimpleNamespace()
    assert agent.get_session_trace("user-a:chat-1") == []
    MathAgent._cache_session_trace(SimpleNamespace(), "user-a:chat-1", _SAMPLE_TRACE)
