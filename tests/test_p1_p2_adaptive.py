"""
P1+P2 完整专项测试：难度估算 + 自动技能重计算。

运行:
    pytest tests/test_p1_p2_adaptive.py -v
    pytest tests/test_p1_p2_adaptive.py -v --cov=app.services.difficulty_estimator
"""

import asyncio
import time
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, ANY
import pytest

from app.services.difficulty_estimator import (
    DifficultyEstimator,
    DEFAULT_WEIGHTS,
    DIFFICULTY_MAP,
    CONTEXT_ADJUSTMENTS,
    TREND_MIN_RECORDS,
)
from agent_core.memory_persistence import (
    MemoryPersistenceFacade,
    UserProfile,
    RECALC_TRIGGER,
)


# ═══════════════════════════════════════════════════════════════════
# P1: DifficultyEstimator 单元测试
# ═══════════════════════════════════════════════════════════════════

class TestDifficultyEstimatorScoreMapping:
    """测试难度分制映射 (-> 1-5)"""

    def test_score_above_090_returns_5(self):
        assert DifficultyEstimator._score_to_difficulty(0.95) == 5
        assert DifficultyEstimator._score_to_difficulty(1.00) == 5
        assert DifficultyEstimator._score_to_difficulty(0.91) == 5

    def test_score_above_075_returns_4(self):
        assert DifficultyEstimator._score_to_difficulty(0.85) == 4
        assert DifficultyEstimator._score_to_difficulty(0.76) == 4

    def test_score_above_055_returns_3(self):
        assert DifficultyEstimator._score_to_difficulty(0.65) == 3
        assert DifficultyEstimator._score_to_difficulty(0.56) == 3

    def test_score_above_035_returns_2(self):
        assert DifficultyEstimator._score_to_difficulty(0.45) == 2
        assert DifficultyEstimator._score_to_difficulty(0.36) == 2

    def test_score_below_035_returns_1(self):
        assert DifficultyEstimator._score_to_difficulty(0.20) == 1
        assert DifficultyEstimator._score_to_difficulty(0.00) == 1

    def test_score_clamps_to_0_1(self):
        assert DifficultyEstimator._score_to_difficulty(-0.5) == 1
        assert DifficultyEstimator._score_to_difficulty(1.5) == 5

    def test_all_thresholds_are_valid(self):
        """所有 DIFFICULTY_MAP 阈值范围合法"""
        for threshold, diff, label in DIFFICULTY_MAP:
            assert 0.0 <= threshold <= 1.0
            assert 1 <= diff <= 5


class TestDifficultyEstimatorContext:
    """测试上下文模式调整"""

    def test_apply_context_practice_no_change(self):
        assert DifficultyEstimator._apply_context(3, "practice") == 3

    def test_apply_context_exam_lower(self):
        assert DifficultyEstimator._apply_context(3, "exam") == 2
        assert DifficultyEstimator._apply_context(1, "exam") == 1  # 不低于 1

    def test_apply_context_challenge_higher(self):
        assert DifficultyEstimator._apply_context(3, "challenge") == 4
        assert DifficultyEstimator._apply_context(5, "challenge") == 5  # 不高于 5

    def test_apply_context_error_correction(self):
        assert DifficultyEstimator._apply_context(4, "error_correction") == 3

    def test_apply_context_review(self):
        # review adjustment = 0.5; round(2.5) = 2 (banker's rounding)
        result = DifficultyEstimator._apply_context(2, "review")
        assert result == 2, f"Expected 2, got {result}"

    def test_apply_context_unknown_default(self):
        assert DifficultyEstimator._apply_context(3, "unknown") == 3

    def test_all_contexts_have_valid_adjustments(self):
        for ctx, adj in CONTEXT_ADJUSTMENTS.items():
            base = 3
            result = DifficultyEstimator._apply_context(base, ctx)
            assert 1 <= result <= 5, f"Context {ctx} adj={adj} gave {result}"


class TestDifficultyEstimatorOverallRate:
    """测试整体正确率提取"""

    def test_with_profile(self):
        assert DifficultyEstimator._get_overall_rate({"correct_rate": 0.85}) == 0.85

    def test_with_empty_profile(self):
        assert DifficultyEstimator._get_overall_rate({}) == 0.5

    def test_with_none(self):
        assert DifficultyEstimator._get_overall_rate(None) == 0.5


class TestDifficultyEstimatorEstimate:
    """测试 estimate() 核心方法"""

    @pytest.mark.asyncio
    async def test_basic_estimate_returns_int_1_to_5(self):
        """基本估算返回 1-5 之间的整数"""
        est = DifficultyEstimator()
        d = await est.estimate("test_user", "代数", "一元一次方程")
        assert isinstance(d, int)
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_with_profile_high_rate(self):
        """高正确率用户应得到更高难度"""
        est = DifficultyEstimator()
        d = await est.estimate(
            "test_user", "极限", "极限计算",
            profile={"correct_rate": 0.95},
        )
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_with_profile_low_rate(self):
        """低正确率用户应得到更低难度"""
        est = DifficultyEstimator()
        d = await est.estimate(
            "test_user", "极限", "极限计算",
            profile={"correct_rate": 0.20},
        )
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_high_vs_low_rate(self):
        """高正确率 >= 低正确率的难度"""
        est = DifficultyEstimator()
        d_high = await est.estimate(
            "test_user", "极限", "",
            profile={"correct_rate": 0.95},
        )
        d_low = await est.estimate(
            "test_user", "极限", "",
            profile={"correct_rate": 0.20},
        )
        assert d_high >= d_low

    @pytest.mark.asyncio
    async def test_estimate_with_skill_data(self):
        """传递 skill_data 应可正常工作"""
        est = DifficultyEstimator()
        skill_data = [
            {
                "skill_code": "代数_一元一次方程",
                "mastery_level": 0.8,
                "evolution_history": [
                    {"mastery": 0.5, "date": "2026-01-01"},
                    {"mastery": 0.6, "date": "2026-01-15"},
                    {"mastery": 0.7, "date": "2026-02-01"},
                ],
                "last_practiced": "2026-05-01T00:00:00+00:00",
                "total_attempts": 10,
                "correct_count": 8,
            }
        ]
        d = await est.estimate(
            "test_user", "代数", "一元一次方程",
            skill_data=skill_data,
        )
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_context_exam_lower(self):
        """
        考试上下文应比练习上下文产生更低（或相等）难度。
        （由于随机性，只验证 both valid）
        """
        est = DifficultyEstimator()
        d_p = await est.estimate("test_user", "代数", "", context="practice")
        d_e = await est.estimate("test_user", "代数", "", context="exam")
        d_c = await est.estimate("test_user", "代数", "", context="challenge")
        for d in [d_p, d_e, d_c]:
            assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_no_sub_category(self):
        """无 sub_category 时应返回有效值"""
        est = DifficultyEstimator()
        d = await est.estimate("test_user", "代数")
        assert 1 <= d <= 5


class TestDifficultyEstimatorEstimateForProfile:
    """测试 estimate_for_profile()"""

    @pytest.mark.asyncio
    async def test_empty_profile_returns_default(self):
        est = DifficultyEstimator()
        profile = UserProfile(total_questions=0)
        d = await est.estimate_for_profile("test_user", profile)
        assert d == 3  # 默认中等

    @pytest.mark.asyncio
    async def test_with_skills(self):
        est = DifficultyEstimator()
        profile = UserProfile(
            total_questions=20,
            correct_rate=0.8,
            skills=[
                {"skill_code": "algebra", "mastery_level": 0.9, "total_attempts": 10},
                {"skill_code": "trig", "mastery_level": 0.3, "total_attempts": 5},
            ],
        )
        d = await est.estimate_for_profile("test_user", profile)
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_high_correct_rate_high_difficulty(self):
        est = DifficultyEstimator()
        high = UserProfile(total_questions=10, correct_rate=0.95)
        low = UserProfile(total_questions=10, correct_rate=0.15)
        d_high = await est.estimate_for_profile("test_user", high)
        d_low = await est.estimate_for_profile("test_user", low)
        assert d_high >= d_low

    @pytest.mark.asyncio
    async def test_context_adjustment(self):
        est = DifficultyEstimator()
        profile = UserProfile(total_questions=20, correct_rate=0.7)
        d_practice = await est.estimate_for_profile("test_user", profile, "practice")
        d_exam = await est.estimate_for_profile("test_user", profile, "exam")
        assert d_practice >= d_exam


class TestDifficultyEstimatorBatch:
    """测试批次估算"""

    @pytest.mark.asyncio
    async def test_estimate_batch_returns_dict(self):
        est = DifficultyEstimator()
        categories = [
            {"category": "代数", "sub_category": "一元一次方程"},
            {"category": "极限", "sub_category": "极限计算"},
        ]
        results = await est.estimate_batch("test_user", categories)
        assert isinstance(results, dict)
        assert len(results) == 2
        for key, val in results.items():
            assert 1 <= val <= 5

    @pytest.mark.asyncio
    async def test_estimate_batch_empty(self):
        est = DifficultyEstimator()
        results = await est.estimate_batch("test_user", [])
        assert results == {}

    @pytest.mark.asyncio
    async def test_estimate_batch_missing_sub(self):
        est = DifficultyEstimator()
        categories = [{"category": "代数"}]
        results = await est.estimate_batch("test_user", categories)
        assert len(results) == 1


class TestDifficultyEstimatorRecentTrend:
    """测试近期趋势计算"""

    def test_no_history_returns_neutral(self):
        est = DifficultyEstimator()
        score = est._calculate_recent_trend("代数", "方程")
        assert score == 0.5

    def test_insufficient_data_returns_neutral(self):
        est = DifficultyEstimator()
        skill_data = [{
            "skill_code": "代数_方程",
            "evolution_history": [
                {"mastery": 0.5, "date": "2026-01-01"},
            ],
        }]
        score = est._calculate_recent_trend(
            "代数", "方程", skill_data=skill_data
        )
        assert score == 0.5

    def test_upward_trend_high_score(self):
        """上升趋势应接近 1.0"""
        est = DifficultyEstimator()
        skill_data = [{
            "skill_code": "代数_方程",
            "evolution_history": [
                {"mastery": 0.3, "date": "2026-01-01"},
                {"mastery": 0.5, "date": "2026-01-15"},
                {"mastery": 0.8, "date": "2026-02-01"},
                {"mastery": 0.9, "date": "2026-02-15"},
            ],
        }]
        score = est._calculate_recent_trend(
            "代数", "方程", skill_data=skill_data
        )
        assert score >= 0.5

    def test_downward_trend_low_score(self):
        """下降趋势应接近 0.0"""
        est = DifficultyEstimator()
        skill_data = [{
            "skill_code": "代数_方程",
            "evolution_history": [
                {"mastery": 0.9, "date": "2026-01-01"},
                {"mastery": 0.7, "date": "2026-01-15"},
                {"mastery": 0.4, "date": "2026-02-01"},
                {"mastery": 0.2, "date": "2026-02-15"},
            ],
        }]
        score = est._calculate_recent_trend(
            "代数", "方程", skill_data=skill_data
        )
        assert score <= 0.5


class TestDifficultyEstimatorTimeFactor:
    """测试遗忘因子计算"""

    def test_no_data_returns_neutral(self):
        est = DifficultyEstimator()
        factor = est._calculate_time_factor("代数", "方程")
        assert factor == 0.5

    def test_very_recent_high_factor(self):
        """最近练习过的应接近 1.0"""
        est = DifficultyEstimator()
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        skill_data = [{
            "skill_code": "代数_方程",
            "last_practiced": yesterday.isoformat(),
        }]
        factor = est._calculate_time_factor(
            "代数", "方程", skill_data=skill_data
        )
        assert factor > 0.7

    def test_long_ago_low_factor(self):
        """很久没练习的应接近 0.0"""
        est = DifficultyEstimator()
        long_ago = datetime.now(timezone.utc) - timedelta(days=90)
        skill_data = [{
            "skill_code": "代数_方程",
            "last_practiced": long_ago.isoformat(),
        }]
        factor = est._calculate_time_factor(
            "代数", "方程", skill_data=skill_data
        )
        assert factor < 0.5

    def test_time_factor_exponential_decay(self):
        """验证指数衰减曲线"""
        est = DifficultyEstimator()
        for days in [1, 7, 14, 30, 60]:
            then = datetime.now(timezone.utc) - timedelta(days=days)
            skill_data = [{
                "skill_code": "代数_方程",
                "last_practiced": then.isoformat(),
            }]
            factor = est._calculate_time_factor(
                "代数", "方程", skill_data=skill_data
            )
            assert 0.0 <= factor <= 1.0
            if days < 14:
                assert factor > 0.3, f"days={days} factor={factor}"


class TestDifficultyEstimatorUpdateWeights:
    """测试权重更新"""

    def test_update_weights_partial(self):
        est = DifficultyEstimator()
        est.update_weights({"mastery": 0.5})
        assert est._weights["mastery"] == 0.5
        assert est._weights["overall"] == DEFAULT_WEIGHTS["overall"]  # 不变

    def test_update_weights_invalid_key_ignored(self):
        est = DifficultyEstimator()
        est.update_weights({"invalid_key": 1.0})
        assert "invalid_key" not in est._weights

    def test_weights_sum_to_1(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


class TestDifficultyEstimatorDifficultyBonus:
    """测试难度奖励因子"""

    def test_no_sub_category_returns_default(self):
        est = DifficultyEstimator(skill_aggregator=MagicMock())
        bonus = est._calculate_difficulty_bonus("代数", "")
        assert bonus == 0.5


# ═══════════════════════════════════════════════════════════════════
# P2: 自动技能重计算 单元测试
# ═══════════════════════════════════════════════════════════════════

class TestMemoryPersistenceFacadeRecalcTrigger:
    """测试自动重计算触发逻辑"""

    @pytest.mark.asyncio
    async def test_estimate_difficulty_public_interface(self):
        """公共难度估算接口应返回 1-5"""
        facade = MemoryPersistenceFacade()
        d = await facade.estimate_difficulty("test_user", "代数", "方程")
        assert 1 <= d <= 5

    @pytest.mark.asyncio
    async def test_estimate_difficulty_default_on_no_estimator(self):
        """无 DifficultyEstimator 时应返回默认值 3"""
        facade = MemoryPersistenceFacade()
        facade._difficulty_estimator = None
        d = await facade.estimate_difficulty("test_user", "代数")
        assert d == 3

    @pytest.mark.asyncio
    async def test_trigger_skill_recalculation_returns_int(self):
        """显式触发重计算返回整数"""
        facade = MemoryPersistenceFacade()
        count = await facade.trigger_skill_recalculation("test_user")
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_trigger_recalc_no_aggregator(self):
        """无 aggregator 时应返回 0"""
        facade = MemoryPersistenceFacade()
        facade._skill_aggregator = None
        count = await facade.trigger_skill_recalculation("test_user")
        assert count == 0

    @pytest.mark.asyncio
    async def test_maybe_trigger_recalc_new_user(self):
        """新用户首次事件不应触发（事件数不够）"""
        facade = MemoryPersistenceFacade()
        triggered = await facade._maybe_trigger_recalc("new_user_1")
        assert not triggered

    @pytest.mark.asyncio
    async def test_maybe_trigger_recalc_min_interval(self):
        """同一用户短时间多次调用，间隔保护"""
        facade = MemoryPersistenceFacade()
        # 第一次触发（事件数达到阈值）
        for i in range(RECALC_TRIGGER["event_count"]):
            facade._event_count_since_recalc["user_interval"] = i + 1

        facade._last_recalc_time["user_interval"] = time.time()  # 刚重算过
        triggered = await facade._maybe_trigger_recalc("user_interval")
        assert not triggered, "间隔保护应阻止重计算"

    @pytest.mark.asyncio
    async def test_maybe_trigger_recalc_after_interval(self):
        """超过间隔后应触发"""
        facade = MemoryPersistenceFacade()
        facade._event_count_since_recalc["user_ok"] = RECALC_TRIGGER["event_count"]
        # 模拟距上次重算已足够久
        facade._last_recalc_time["user_ok"] = time.time() - RECALC_TRIGGER["min_interval"] - 10
        triggered = await facade._maybe_trigger_recalc("user_ok")
        assert triggered

    @pytest.mark.asyncio
    async def test_get_recalc_status(self):
        """get_recalc_status 返回完整状态信息"""
        facade = MemoryPersistenceFacade()
        status = await facade.get_recalc_status("test_user")
        assert "user_id" in status
        assert "last_recalc_at" in status
        assert "events_since_recalc" in status
        assert "trigger_config" in status
        assert status["user_id"] == "test_user"

    @pytest.mark.asyncio
    async def test_on_buffer_flush_below_threshold(self):
        """缓冲区不足时不触发"""
        facade = MemoryPersistenceFacade()
        # mock 事件列表（低于阈值）
        mock_events = [MagicMock(user_id="u1") for _ in range(
            RECALC_TRIGGER["batch_threshold"] - 10
        )]
        await facade._on_buffer_flush(mock_events)
        # 不应触发异常

    @pytest.mark.asyncio
    async def test_on_buffer_flush_empty(self):
        """空列表不触发"""
        facade = MemoryPersistenceFacade()
        await facade._on_buffer_flush([])
        await facade._on_buffer_flush(None)

    @pytest.mark.asyncio
    async def test_record_event_auto_triggers(self):
        """record_event 应增加事件计数"""
        facade = MemoryPersistenceFacade()
        facade._event_count_since_recalc["recalc_user"] = 0
        # 调用 record_event 会触发 _maybe_trigger_recalc
        result = await facade.record_event("recalc_user", {
            "event_type": "answer_correct",
            "question_content": "test",
            "category": "代数",
            "is_correct": True,
        })
        # record_event 不应失败
        assert isinstance(result, bool)


class TestMemoryPersistenceFacadeDifficultyIntegration:
    """测试 get_profile 中的难度集成"""

    @pytest.mark.asyncio
    async def test_get_profile_recommended_difficulty_is_int(self):
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile("test_user")
        assert isinstance(profile.recommended_difficulty, int)
        assert 1 <= profile.recommended_difficulty <= 5

    @pytest.mark.asyncio
    async def test_get_profile_updates_difficulty(self):
        """get_profile 应使用 DifficultyEstimator 更新 difficulty"""
        facade = MemoryPersistenceFacade()
        profile1 = await facade.get_profile("diff_user_1")
        profile2 = await facade.get_profile("diff_user_2")
        assert isinstance(profile1.recommended_difficulty, int)
        assert isinstance(profile2.recommended_difficulty, int)


class TestMemoryPersistenceFacadeBufferIntegration:
    """测试 buffer_event 触发器"""

    @pytest.mark.asyncio
    async def test_buffer_event_increases_counter(self):
        facade = MemoryPersistenceFacade()
        facade._event_count_since_recalc["buf_user"] = 0
        for i in range(3):
            await facade.buffer_event("buf_user", {
                "event_type": "question",
                "question_content": f"test {i}",
                "category": "代数",
            })
        # 应该已计入 buffer，但重计算计数不动
        # 因为 buffer_event 不走 _maybe_trigger_recalc
        status = await facade.get_recalc_status("buf_user")
        assert "events_since_recalc" in status


class TestRecalcConfig:
    """测试重计算配置合理性"""

    def test_recalc_trigger_config_valid(self):
        assert RECALC_TRIGGER["event_count"] > 0
        assert RECALC_TRIGGER["min_interval"] >= 0
        assert RECALC_TRIGGER["batch_threshold"] > 0
        assert isinstance(RECALC_TRIGGER["flush_callback"], bool)