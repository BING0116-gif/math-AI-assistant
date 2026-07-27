"""
P0-01: MemoryExtractor 自动记忆提取器专项测试。

测试覆盖：
- 数学题提取（导数、极限、积分等各类知识点）
- 非数学题跳过
- 错误信息提取
- 正确性判断（精确匹配、数字交集）
- 工具调用提取
- 超长文本截断
- 空结果处理

运行: pytest tests/test_memory_extractor.py -v
"""

import pytest
from agent_core.memory_extractor import MemoryExtractor, LearningEvent, get_memory_extractor


class TestLearningEvent:
    """LearningEvent 数据结构测试。"""

    def test_to_dict_basic(self):
        event = LearningEvent(
            user_id="u1", event_type="problem_solving",
            question_content="求导数", category="导数",
            sub_categories=["求导"], user_answer="2x", correct_answer="2x",
        )
        d = event.to_dict()
        assert d["user_id"] == "u1"
        assert d["is_correct"] == ""
        assert d["tools_used"] == []

    def test_to_dict_none_handling(self):
        event = LearningEvent(
            user_id="u1", event_type="problem_solving",
            question_content="q", category="c",
            sub_categories=[], user_answer="", correct_answer="",
            is_correct=None,
        )
        d = event.to_dict()
        assert d["is_correct"] == ""


class TestMemoryExtractor:
    """MemoryExtractor 核心逻辑测试。"""

    @pytest.mark.asyncio
    async def test_extract_derivative(self):
        """测试导数题提取。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="求导 f(x) = x^2",
            agent_result={
                "answer": "f'(x) = 2x",
                "thoughts": [{"type": "action", "tool": "calculator"}],
                "metadata": {},
            },
            execution_time=2.5,
        )
        assert event is not None
        assert event.category == "导数"
        assert "calculator" in event.tools_used
        assert event.event_type == "problem_solving"
        assert event.time_spent == 2.5

    @pytest.mark.asyncio
    async def test_extract_limit(self):
        """测试极限题提取。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="求极限 lim(x->0) sin(x)/x",
            agent_result={
                "answer": "1",
                "thoughts": [],
                "metadata": {},
            },
            execution_time=1.0,
        )
        assert event is not None
        assert event.category == "极限"

    @pytest.mark.asyncio
    async def test_extract_integral(self):
        """测试积分题提取。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="求定积分 x dx 从0到1",
            agent_result={
                "answer": "0.5",
                "thoughts": [],
                "metadata": {},
            },
            execution_time=3.0,
        )
        assert event is not None
        assert event.category == "积分"

    @pytest.mark.asyncio
    async def test_skip_concept(self):
        """测试概念题跳过（非数学解题类）。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="什么是机器学习？",
            agent_result={"answer": "...", "thoughts": [], "metadata": {}},
            execution_time=1.0,
        )
        assert event is None

    @pytest.mark.asyncio
    async def test_skip_greeting(self):
        """测试问候语跳过。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="你好，今天天气不错",
            agent_result={"answer": "你好！", "thoughts": [], "metadata": {}},
            execution_time=0.5,
        )
        assert event is None

    @pytest.mark.asyncio
    async def test_error_extraction(self):
        """测试错误信息提取。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="求极限 lim(x->0) sin(x)/x",
            agent_result={
                "answer": "0",
                "thoughts": [],
                "metadata": {
                    "correct_answer": "1",
                    "error_category": "计算错误",
                    "error_reason": "忘记极限公式",
                    "correction_suggestion": "sin(x)/x 的极限是1",
                },
            },
            execution_time=3.0,
        )
        assert event is not None
        assert event.is_correct is False
        assert event.error_category == "计算错误"
        assert event.error_reason == "忘记极限公式"
        assert event.correction_suggestion == "sin(x)/x 的极限是1"

    @pytest.mark.asyncio
    async def test_correct_answer_exact_match(self):
        """测试精确匹配正确性判断。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="计算 2+2 等于多少",
            agent_result={
                "answer": "4",
                "thoughts": [],
                "metadata": {"correct_answer": "4"},
            },
            execution_time=0.5,
        )
        assert event is not None
        assert event.is_correct is True

    @pytest.mark.asyncio
    async def test_no_correct_answer(self):
        """测试无标准答案时正确性为None。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="求导 f(x) = 2x + 1",
            agent_result={
                "answer": "2",
                "thoughts": [],
                "metadata": {},
            },
            execution_time=1.0,
        )
        assert event is not None
        assert event.is_correct is None

    @pytest.mark.asyncio
    async def test_tool_extraction(self):
        """测试工具调用提取。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="解方程 x^2 = 4",
            agent_result={
                "answer": "x=2 或 x=-2",
                "thoughts": [
                    {"type": "action", "tool": "calculator"},
                    {"type": "action", "tool": "wolfram"},
                    {"type": "observation", "content": "提示：考虑正负根"},
                ],
                "metadata": {},
            },
            execution_time=2.0,
        )
        assert event is not None
        assert "calculator" in event.tools_used
        assert "wolfram" in event.tools_used
        assert len(event.tools_used) == 2
        assert event.hint_count == 1

    @pytest.mark.asyncio
    async def test_text_truncation(self):
        """测试超长文本截断。"""
        long_input = "求导 " + "x" * 1000
        long_answer = "f'(x) = " + "x" * 500
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input=long_input,
            agent_result={
                "answer": long_answer,
                "thoughts": [],
                "metadata": {"correct_answer": "2x"},
            },
            execution_time=1.0,
        )
        assert event is not None
        assert len(event.question_content) <= 500
        assert len(event.user_answer) <= 200

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """测试空结果处理。"""
        extractor = MemoryExtractor()
        event = await extractor.extract_from_agent_result(
            user_id="u1",
            user_input="解方程 x + 2 = 5",
            agent_result={},
            execution_time=0.0,
        )
        assert event is not None
        assert event.tools_used == []

    def test_singleton(self):
        """测试单例工厂。"""
        e1 = get_memory_extractor()
        e2 = get_memory_extractor()
        assert e1 is e2

    def test_extract_category(self):
        """测试知识点分类提取。"""
        extractor = MemoryExtractor()
        cat, subs = extractor._extract_category("求矩阵的行列式")
        assert cat == "线性代数"
        assert "矩阵" in subs

        cat, subs = extractor._extract_category("求函数的定义域")
        assert cat == "函数"
        assert "定义域" in subs

        cat, subs = extractor._extract_category("普通问题")
        assert cat == "未知"
        assert subs == []

    def test_judge_correctness(self):
        """测试正确性判断逻辑。"""
        extractor = MemoryExtractor()
        assert extractor._judge_correctness("4", "4") is True
        assert extractor._judge_correctness("4", "5") is False
        assert extractor._judge_correctness("", "4") is None
        assert extractor._judge_correctness("4", "") is None
        assert extractor._judge_correctness("", "") is None
        assert extractor._judge_correctness("x=2", "x=2") is True

    def test_is_math_problem(self):
        """测试数学题判断。"""
        extractor = MemoryExtractor()
        assert extractor._is_math_problem("求导 f(x) = x^2") is True
        assert extractor._is_math_problem("解方程 x + 2 = 5") is True
        assert extractor._is_math_problem("什么是机器学习") is False
        assert extractor._is_math_problem("你好，今天天气不错") is False
