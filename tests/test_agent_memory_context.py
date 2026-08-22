import asyncio
from types import SimpleNamespace

from agent_core.agent import MathAgent


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
