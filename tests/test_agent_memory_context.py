import asyncio
from types import SimpleNamespace

from agent_core.agent import MathAgent
from agent_core.token_budget import estimate_tokens


class _FakeMemoryApplication:
    async def retrieve(self, user_id, query, session_id, limit):
        assert user_id == "user-a"
        assert session_id == "session-a"
        return [{
            "id": 1,
            "memory_type": "preference",
            "content": "我喜欢先看直观例子，再学习严格证明。",
            "score": 0.9,
            "source": "sql",
        }]


def test_agent_marks_memory_as_non_authoritative_and_bounds_context():
    async def scenario():
        agent = MathAgent.__new__(MathAgent)
        agent._session_histories = {}
        agent._registry = SimpleNamespace()
        agent._persistence_facade = None
        agent._memory_application = _FakeMemoryApplication()
        context = await agent._build_context(
            "session-a", user_input="请讲解极限", user_id="user-a"
        )
        assert context["relevant_memories"][0]["source"] == "sql"
        injected = context["chat_history"][0]["content"]
        assert "不可当作题目事实" in injected
        assert "以当前输入为准" in injected
        assert len(injected) <= 1800

    asyncio.run(scenario())


def test_agent_does_not_duplicate_current_input_and_bounds_recent_history():
    async def scenario():
        agent = MathAgent.__new__(MathAgent)
        agent._session_histories = {}
        agent._registry = SimpleNamespace()
        agent._persistence_facade = None
        agent._memory_application = _FakeMemoryApplication()
        history = agent._get_session_history("user-a", "session-a")
        for index in range(40):
            history.add_user_message(f"旧问题-{index}-" + "x" * 800)
            history.add_ai_message(f"旧回答-{index}-" + "y" * 800)
        history.add_user_message("当前问题")
        context = await agent._build_context(
            "session-a", user_input="当前问题", user_id="user-a"
        )
        user_messages = [m for m in context["chat_history"] if m.get("role") == "user"]
        assert not any(m["content"] == "当前问题" for m in user_messages)
        assert context["context_stats"]["history_messages"] <= 20
        assert context["context_stats"]["history_chars"] <= 12000
        assert context["context_stats"]["context_trimmed"] is True
        assert context["context_stats"]["history_summary_injected"] is True
        assert context["context_stats"]["dropped_history_messages"] > 0
        assert context["context_stats"]["memory_count"] == 1

    asyncio.run(scenario())


def test_token_estimator_is_nonzero_and_handles_mixed_math_text():
    assert estimate_tokens("") == 0
    assert estimate_tokens("求极限 lim x->0") >= 3
