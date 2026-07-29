"""
LLM复杂度分类器 — 单元测试与集成测试

使用方法:
    cd "math AI assistant"
    python -m pytest tests/test_classifier.py -v -s
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from prompts.classifier_prompt import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
)
from agent_core.classifier.llm_classifier import (
    ClassifierConfig,
    ClassificationResult,
    LLMComplexityClassifier,
)


class TestComplexityLevels:
    def test_enum_values(self):
        assert ComplexityLevel.TRIVIAL == 1
        assert ComplexityLevel.BASIC == 2
        assert ComplexityLevel.MODERATE == 3
        assert ComplexityLevel.ADVANCED == 4
        assert ComplexityLevel.COMPLEX == 5

    def test_label_mapping(self):
        assert ComplexityCategory.get_label(1) == "极简"
        assert ComplexityCategory.get_label(3) == "中等"
        assert ComplexityCategory.get_label(5) == "困难"

    def test_level_to_strategy(self):
        assert level_to_strategy(1) == "react"
        assert level_to_strategy(2) == "react"
        assert level_to_strategy(3) == "react"
        assert level_to_strategy(4) == "planned"
        assert level_to_strategy(5) == "planned"

    def test_level_to_strategy_invalid(self):
        with pytest.raises(ValueError):
            level_to_strategy(0)
        with pytest.raises(ValueError):
            level_to_strategy(6)

    def test_is_simple(self):
        assert is_simple(1) is True
        assert is_simple(3) is True
        assert is_simple(4) is False
        assert is_simple(5) is False

    def test_is_complex(self):
        assert is_complex(1) is False
        assert is_complex(3) is False
        assert is_complex(4) is True
        assert is_complex(5) is True


class TestOutputParser:
    def setup_method(self):
        self.parser = RobustOutputParser()

    def test_perfect_output(self):
        score, conf = self.parser.parse("3")
        assert score == 3
        assert conf == 1.0

    def test_digit_with_punctuation(self):
        score, conf = self.parser.parse("4.")
        assert score == 4
        assert conf >= 0.9

    def test_phrase_answer(self):
        score, conf = self.parser.parse("答案是2")
        assert score == 2
        assert conf >= 0.8

    def test_phrase_difficulty_level(self):
        score, conf = self.parser.parse("难度等级: 3")
        assert score == 3
        assert conf >= 0.8

    def test_chinese_number(self):
        score, conf = self.parser.parse("三")
        assert score == 3
        assert conf == 0.65

    def test_range_expression(self):
        score, conf = self.parser.parse("介于3-4之间")
        assert score == 4
        assert conf == 0.60

    def test_range_or(self):
        score, conf = self.parser.parse("3或4都可以")
        assert score == 4
        assert conf == 0.60

    def test_embedded_digit(self):
        score, conf = self.parser.parse("我认为大概是3分左右")
        assert score == 3
        assert conf >= 0.7

    def test_empty_input(self):
        score, conf = self.parser.parse("")
        assert score == 3
        assert conf == 0.0

    def test_no_digit_fallback(self):
        score, conf = self.parser.parse("这个问题太难了")
        assert score == 3
        assert conf == 0.0

    def test_parse_with_validation_normal(self):
        score, conf = self.parser.parse_with_validation("2")
        assert score == 2
        assert conf == 1.0

    def test_parse_with_validation_out_of_range(self):
        score, conf = self.parser.parse_with_validation("9")
        assert 1 <= score <= 5
        assert conf <= 0.5


class TestPromptTemplates:
    def test_system_prompt_not_empty(self):
        assert len(CLASSIFICATION_SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_levels(self):
        assert "1分" in CLASSIFICATION_SYSTEM_PROMPT
        assert "5分" in CLASSIFICATION_SYSTEM_PROMPT
        assert "只要回答" in CLASSIFICATION_SYSTEM_PROMPT

    def test_build_messages(self):
        messages = ClassificationPromptTemplate.build("1+1=?")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "1+1=?" in messages[1]["content"]


class TestClassifierConfig:
    def test_default_config(self):
        config = ClassifierConfig()
        assert config.cache_max_size == 2000
        assert config.enable_cache is True
        assert config.enable_fallback is True
        assert config.classification_timeout == 5.0
        assert config.temperature == 0.0

    def test_custom_config(self):
        config = ClassifierConfig(cache_max_size=500, classification_timeout=3.0)
        assert config.cache_max_size == 500
        assert config.classification_timeout == 3.0


class TestClassificationResult:
    def test_result_creation(self):
        result = ClassificationResult(
            score=4,
            confidence=0.85,
            strategy="planned",
            reasoning="test",
            method="llm",
            latency_ms=150.0,
        )
        assert result.score == 4
        assert result.strategy == "planned"

    def test_result_to_dict(self):
        result = ClassificationResult(
            score=2, confidence=0.9, strategy="react",
            reasoning="test", method="llm",
        )
        d = result.to_dict()
        assert d["score"] == 2
        assert d["strategy"] == "react"
        assert d["method"] == "llm"

    def test_result_repr(self):
        result = ClassificationResult(
            score=5, confidence=0.8, strategy="planned",
            reasoning="test", method="llm",
        )
        repr_str = repr(result)
        assert "5" in repr_str
        assert "planned" in repr_str


@pytest.mark.integration
@pytest.mark.asyncio
class TestLLMClassifierIntegration:
    """
    集成测试 — 使用 mock LLM。

    运行方式:
        python -m pytest tests/test_classifier.py -v -s -m integration
    """

    async def _create_classifier(self, mock_score: int = 3):
        from agent_core.classifier.llm_classifier import LLMComplexityClassifier, ClassifierConfig

        mock_llm = AsyncMock()
        # 模拟 LLM 返回格式化的分类结果
        mock_llm.ainvoke.return_value = MagicMock(
            content=f"{mock_score}\n中等\nreact\n数学问题分类结果",
        )

        config = ClassifierConfig(
            enable_cache=True,
            enable_fallback=True,
            classification_timeout=5.0,
            temperature=0.0,
        )

        return LLMComplexityClassifier(llm=mock_llm, config=config)

    async def test_classify_trivial(self):
        classifier = await self._create_classifier(mock_score=1)
        result = await classifier.classify("1+1等于几？")
        assert 1 <= result.score <= 2, f"期望1-2分, 得到{result.score}"
        assert result.strategy == "react"
        print(f"✅ 极简分类: {result}")

    async def test_classify_basic(self):
        classifier = await self._create_classifier(mock_score=2)
        result = await classifier.classify("求 f(x)=x³ 的导数")
        assert 1 <= result.score <= 3, f"期望1-3分, 得到{result.score}"
        print(f"✅ 基础分类: {result}")

    async def test_classify_moderate(self):
        classifier = await self._create_classifier(mock_score=3)
        result = await classifier.classify("用分部积分求∫x·eˣdx")
        assert 2 <= result.score <= 4, f"期望2-4分, 得到{result.score}"
        print(f"✅ 中等分类: {result}")

    async def test_classify_advanced(self):
        classifier = await self._create_classifier(mock_score=4)
        result = await classifier.classify("证明: eˣ > x+1 对所有 x≠0 成立")
        assert 3 <= result.score <= 5, f"期望3-5分, 得到{result.score}"
        print(f"✅ 较难分类: {result}")

    async def test_classify_complex(self):
        classifier = await self._create_classifier(mock_score=5)
        result = await classifier.classify("证明闭区间上连续函数必一致连续")
        assert 3 <= result.score <= 5, f"期望3-5分, 得到{result.score}"
        print(f"✅ 困难分类: {result}")

    async def test_cache_hit(self):
        classifier = await self._create_classifier()

        result1 = await classifier.classify("解方程 x²-4=0")
        assert result1.method == "llm"

        result2 = await classifier.classify("解方程 x²-4=0")
        assert result2.method == "cache"
        assert result2.score == result1.score

        stats = classifier.get_stats()
        assert stats["cache_hits"] >= 1

        print(f"✅ 缓存测试通过: {stats}")

    async def test_is_complex_problem(self):
        mock_llm = AsyncMock()

        async def side_effect(messages):
            problem = messages[-1].content if messages else ""
            if "sin" in problem:
                return MagicMock(content="1\n极简\nreact\n简单三角函数")
            return MagicMock(content="4\n较难\nplanned\n需要证明方法")

        mock_llm.ainvoke.side_effect = side_effect
        config = ClassifierConfig(enable_cache=True, enable_fallback=True)
        classifier = LLMComplexityClassifier(llm=mock_llm, config=config)

        is_simple_result = await classifier.is_complex_problem("sin(π/6)=?")
        assert is_simple_result is False

        is_complex_result = await classifier.is_complex_problem(
            "证明: π是无理数"
        )
        assert is_complex_result is True

        print("✅ is_complex_problem 测试通过")

    async def test_batch_classify(self):
        classifier = await self._create_classifier()

        problems = [
            "1+1=?",
            "求∫x²dx",
            "证明eˣ > x+1",
        ]

        results = await classifier.batch_classify(problems, max_concurrency=2)
        assert len(results) == 3

        for problem, result in zip(problems, results):
            assert 1 <= result.score <= 5
            print(f"  '{problem[:30]}...' → score={result.score} ({result.strategy})")

        print("✅ 批量分类测试通过")

    async def test_stats(self):
        classifier = await self._create_classifier()
        await classifier.classify("1+1=?")
        await classifier.classify("求∫x²dx")

        stats = classifier.get_stats()
        assert stats["total_calls"] >= 2
        assert "cache_hit_rate" in stats
        assert "error_rate" in stats

        print(f"✅ 统计信息: {stats}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
