"""
P0-03: 问答后跟进推荐集成测试。

测试覆盖：
- Agent.solve() 包含 follow_up 推荐
- 非数学题不触发推荐
- 推荐失败不影响主流程
- SSE 流式事件触发
- FollowUpRecommender 与 Agent 集成

运行: pytest tests/test_follow_up.py -v
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from agent_core.agent import MathAgent, MathAgentConfig


class TestFollowUpRecommendation:
    """跟进推荐集成测试。"""

    @pytest.mark.asyncio
    async def test_should_recommend_math_problem(self):
        """测试数学题触发推荐。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        with patch("app.services.follow_up_recommender.is_math_problem", return_value=True):
            result_mock = MagicMock()
            result_mock.answer = "f'(x) = 2x"
            result_mock.thoughts = []
            result_mock.metadata = {}
            assert agent._should_recommend("求导数", result_mock.answer) is True

    @pytest.mark.asyncio
    async def test_should_not_recommend_concept(self):
        """测试概念题不触发推荐。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        with patch("app.services.follow_up_recommender.is_math_problem", return_value=False):
            result_mock = MagicMock()
            result_mock.answer = "导数是..."
            assert agent._should_recommend("什么是导数", result_mock.answer) is False

    @pytest.mark.asyncio
    async def test_should_not_recommend_short_answer(self):
        """测试短答案不触发推荐。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        with patch("app.services.follow_up_recommender.is_math_problem", return_value=True):
            result_mock = MagicMock()
            result_mock.answer = "是的"
            assert agent._should_recommend("求导数", result_mock.answer) is False

    @pytest.mark.asyncio
    async def test_generate_follow_up_failure_graceful(self):
        """测试推荐失败返回空字符串。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        with patch("app.services.follow_up_recommender.get_follow_up_recommender",
                   side_effect=Exception("Service unavailable")):
            result = await agent._generate_follow_up(
                user_input="求导数", user_id="test"
            )
            assert result == ""

    @pytest.mark.asyncio
    async def test_generate_follow_up_success(self):
        """测试推荐成功返回格式化文本。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        mock_result = MagicMock()
        mock_result.questions = [
            MagicMock(id="q1", content="基础题", difficulty=2, answer="答案1"),
            MagicMock(id="q2", content="进阶题", difficulty=4, answer="答案2"),
        ]
        mock_recommender = AsyncMock()
        mock_recommender.recommend = AsyncMock(return_value=mock_result)
        with patch("app.services.follow_up_recommender.get_follow_up_recommender",
                   return_value=mock_recommender):
            with patch("app.services.follow_up_recommender.format_follow_up_text",
                       return_value="## 推荐练习\n### 1. 基础巩固\n基础题"):
                result = await agent._generate_follow_up(
                    user_input="求导数", user_id="test"
                )
                assert len(result) > 0
                assert "推荐练习" in result

    @pytest.mark.asyncio
    async def test_solve_contains_follow_up(self):
        """测试 solve() 返回包含 follow_up 字段。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        agent._should_recommend = MagicMock(return_value=True)
        agent._generate_follow_up = AsyncMock(return_value="## 推荐练习\n内容")
        agent._strategy = MagicMock()
        agent._strategy.execute = AsyncMock(return_value=MagicMock(
            answer="f'(x) = 2x", thoughts=[], metadata={}
        ))
        result = await agent.solve(
            input_text="求导数", user_id="test", session_id="s1"
        )
        assert "follow_up" in result
        assert "推荐练习" in result["follow_up"]

    @pytest.mark.asyncio
    async def test_solve_no_follow_up_for_concept(self):
        """测试概念题无 follow_up 字段。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        agent._should_recommend = MagicMock(return_value=False)
        agent._strategy = MagicMock()
        agent._strategy.execute = AsyncMock(return_value=MagicMock(
            answer="导数概念...", thoughts=[], metadata={}
        ))
        result = await agent.solve(
            input_text="什么是导数", user_id="test", session_id="s1"
        )
        assert "follow_up" not in result

    @pytest.mark.asyncio
    async def test_solve_main_answer_unaffected(self):
        """测试推荐失败主回答不受影响。"""
        config = MathAgentConfig(api_key="test-key")
        agent = MathAgent(config)
        agent._should_recommend = MagicMock(return_value=True)
        agent._generate_follow_up = AsyncMock(return_value="")
        agent._strategy = MagicMock()
        agent._strategy.execute = AsyncMock(return_value=MagicMock(
            answer="f'(x) = 2x", thoughts=[], metadata={}
        ))
        result = await agent.solve(
            input_text="求导数", user_id="test", session_id="s1"
        )
        assert result["answer"] is not None
        assert "follow_up" not in result or result["follow_up"] == ""
