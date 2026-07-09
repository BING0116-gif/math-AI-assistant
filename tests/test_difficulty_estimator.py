"""
DifficultyEstimator 单元测试。

覆盖：
- 评分到难度的映射
- 上下文调整
- 四因子加权评分
- 边界条件和默认值
- 批次估算
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.services.difficulty_estimator import (
    DifficultyEstimator,
    DEFAULT_WEIGHTS,
    CONTEXT_ADJUSTMENTS,
)


class TestScoreToDifficulty:
    """测试 _score_to_difficulty 静态方法"""

    def test_challenge_level(self):
        assert DifficultyEstimator._score_to_difficulty(0.95) == 5
        assert DifficultyEstimator._score_to_difficulty(0.90) == 5

    def test_advanced_level(self):
        assert DifficultyEstimator._score_to_difficulty(0.80) == 4
        assert DifficultyEstimator._score_to_difficulty(0.75) == 4

    def test_standard_level(self):
        assert DifficultyEstimator._score_to_difficulty(0.65) == 3
        assert DifficultyEstimator._score_to_difficulty(0.55) == 3

    def test_basic_level(self):
        assert DifficultyEstimator._score_to_difficulty(0.45) == 2
        assert DifficultyEstimator._score_to_difficulty(0.35) == 2

    def test_beginner_level(self):
        assert DifficultyEstimator._score_to_difficulty(0.20) == 1
        assert DifficultyEstimator._score_to_difficulty(0.0) == 1

    def test_boundary_values(self):
        assert DifficultyEstimator._score_to_difficulty(1.0) == 5
        assert DifficultyEstimator._score_to_difficulty(0.0) == 1
        # 超出范围的值应被 clamp
        assert DifficultyEstimator._score_to_difficulty(1.5) == 5
        assert DifficultyEstimator._score_to_difficulty(-0.5) == 1


class TestApplyContext:
    """测试 _apply_context 静态方法"""

    def test_exam_mode_lowers_difficulty(self):
        orig = 4
        adjusted = DifficultyEstimator._apply_context(orig, "exam")
        assert adjusted <= orig

    def test_challenge_mode_raises_difficulty(self):
        orig = 2
        adjusted = DifficultyEstimator._apply_context(orig, "challenge")
        assert adjusted >= orig

    def test_practice_mode_unchanged(self):
        orig = 3
        adjusted = DifficultyEstimator._apply_context(orig, "practice")
        assert adjusted == orig

    def test_error_correction_lowers_significantly(self):
        orig = 4
        adjusted = DifficultyEstimator._apply_context(orig, "error_correction")
        assert adjusted <= orig

    def test_clamped_to_valid_range(self):
        assert 1 <= DifficultyEstimator._apply_context(1, "error_correction") <= 5
        assert 1 <= DifficultyEstimator._apply_context(5, "challenge") <= 5


class TestGetOverallRate:
    """测试 _get_overall_rate 静态方法"""

    def test_with_valid_profile(self):
        profile = {"correct_rate": 0.85}
        assert DifficultyEstimator._get_overall_rate(profile) == 0.85

    def test_with_none_profile(self):
        assert DifficultyEstimator._get_overall_rate(None) == 0.5

    def test_with_missing_key(self):
        assert DifficultyEstimator._get_overall_rate({}) == 0.5


class TestDifficultyEstimator:
    """测试 DifficultyEstimator 实例方法"""

    @pytest.fixture
    def estimator(self):
        return DifficultyEstimator()

    def test_init_default_weights(self, estimator):
        assert estimator._weights == DEFAULT_WEIGHTS

    def test_update_weights(self, estimator):
        estimator.update_weights({"mastery": 0.5, "overall": 0.1})
        assert estimator._weights["mastery"] == 0.5
        assert estimator._weights["overall"] == 0.1
        # 未指定的权重不变
        assert estimator._weights["trend"] == DEFAULT_WEIGHTS["trend"]

    def test_update_weights_invalid_key(self, estimator):
        estimator.update_weights({"nonexistent": 0.99})
        assert "nonexistent" not in estimator._weights

    @pytest.mark.asyncio
    async def test_estimate_no_sub_category_defaults(self, estimator):
        """无子分类时返回默认难度"""
        result = await estimator.estimate(
            user_id="test_user",
            category="calculus",
            sub_category="",
        )
        # 无子分类时，掌握度默认 0.5，加上其他因子，应该在 1-5 之间
        assert 1 <= result <= 5

    @pytest.mark.asyncio
    async def test_estimate_with_skill_data(self, estimator):
        """使用 skill_data 参数进行估算"""
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "mastery_level": 0.8,
                "total_attempts": 10,
                "correct_count": 8,
                "evolution_history": [
                    {"mastery": 0.6},
                    {"mastery": 0.7},
                    {"mastery": 0.8},
                ],
                "last_practiced": "2026-07-04T10:00:00+00:00",
            }
        ]
        result = await estimator.estimate(
            user_id="test_user",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert 1 <= result <= 5

    @pytest.mark.asyncio
    async def test_estimate_with_context(self, estimator):
        """不同上下文模式影响难度"""
        result_practice = await estimator.estimate(
            user_id="test_user",
            category="calculus",
            sub_category="integration",
            context="practice",
        )
        result_exam = await estimator.estimate(
            user_id="test_user",
            category="calculus",
            sub_category="integration",
            context="exam",
        )
        # 考试模式难度应 ≤ 练习模式
        assert result_exam <= result_practice

    @pytest.mark.asyncio
    async def test_estimate_batch(self, estimator):
        """批次估算多个知识点"""
        categories = [
            {"category": "calculus", "sub_category": "integration"},
            {"category": "calculus", "sub_category": "derivative"},
            {"category": "algebra", "sub_category": "matrix"},
        ]
        results = await estimator.estimate_batch(
            user_id="test_user",
            categories=categories,
        )
        assert len(results) == 3
        for key, difficulty in results.items():
            assert 1 <= difficulty <= 5

    @pytest.mark.asyncio
    async def test_estimate_for_profile_no_data(self, estimator):
        """无数据用户返回默认难度"""
        mock_profile = Mock()
        mock_profile.total_questions = 0
        result = await estimator.estimate_for_profile(
            user_id="test_user",
            profile=mock_profile,
        )
        assert result == 3

    @pytest.mark.asyncio
    async def test_estimate_for_profile_with_skills(self, estimator):
        """有技能数据的用户画像估算"""
        mock_profile = Mock()
        mock_profile.total_questions = 10
        mock_profile.correct_rate = 0.75
        mock_profile.skills = [
            {"skill_code": "calc_int", "mastery_level": 0.8, "total_attempts": 5},
            {"skill_code": "calc_der", "mastery_level": 0.6, "total_attempts": 3},
        ]
        result = await estimator.estimate_for_profile(
            user_id="test_user",
            profile=mock_profile,
        )
        assert 1 <= result <= 5


class TestRecentTrend:
    """测试近期趋势计算"""

    @pytest.fixture
    def estimator(self):
        return DifficultyEstimator()

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_neutral(self, estimator):
        """数据不足时返回中性值 0.5"""
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "evolution_history": [{"mastery": 0.7}],  # 只有1条记录
            }
        ]
        result = await estimator._calculate_recent_trend(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_rising_trend(self, estimator):
        """上升趋势返回高分"""
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "evolution_history": [
                    {"mastery": 0.3},
                    {"mastery": 0.5},
                    {"mastery": 0.7},
                ],
            }
        ]
        result = await estimator._calculate_recent_trend(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result > 0.5  # 上升趋势

    @pytest.mark.asyncio
    async def test_falling_trend(self, estimator):
        """下降趋势返回低分"""
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "evolution_history": [
                    {"mastery": 0.8},
                    {"mastery": 0.5},
                    {"mastery": 0.3},
                ],
            }
        ]
        result = await estimator._calculate_recent_trend(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result < 0.5  # 下降趋势

    @pytest.mark.asyncio
    async def test_no_skill_data_returns_neutral(self, estimator):
        """无 skill_data 时返回中性值"""
        result = await estimator._calculate_recent_trend(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=[],
        )
        assert result == 0.5


class TestTimeFactor:
    """测试遗忘因子计算"""

    @pytest.fixture
    def estimator(self):
        return DifficultyEstimator()

    @pytest.mark.asyncio
    async def test_no_data_returns_neutral(self, estimator):
        result = await estimator._calculate_time_factor(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=[],
        )
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_recent_practice_high_score(self, estimator):
        """最近练习过 → 高分"""
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "last_practiced": recent,
            }
        ]
        result = await estimator._calculate_time_factor(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result > 0.8  # 最近练习，遗忘因子高

    @pytest.mark.asyncio
    async def test_old_practice_low_score(self, estimator):
        """很久没练习 → 低分"""
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "last_practiced": old,
            }
        ]
        result = await estimator._calculate_time_factor(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result < 0.3  # 很久没练习，遗忘因子低


class TestCategoryMastery:
    """测试知识点掌握度获取"""

    @pytest.fixture
    def estimator(self):
        return DifficultyEstimator()

    @pytest.mark.asyncio
    async def test_no_sub_category_returns_default(self, estimator):
        result = await estimator._get_category_mastery(
            user_id="test",
            category="calculus",
            sub_category="",
        )
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_with_skill_data_finds_match(self, estimator):
        skill_data = [
            {
                "skill_code": "calculus_integration",
                "mastery_level": 0.75,
            }
        ]
        result = await estimator._get_category_mastery(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result == 0.75

    @pytest.mark.asyncio
    async def test_with_skill_data_no_match(self, estimator):
        skill_data = [
            {
                "skill_code": "algebra_matrix",
                "mastery_level": 0.9,
            }
        ]
        result = await estimator._get_category_mastery(
            user_id="test",
            category="calculus",
            sub_category="integration",
            skill_data=skill_data,
        )
        assert result == 0.5  # 默认值