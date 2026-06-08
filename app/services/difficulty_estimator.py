"""
动态难度估算器 — 基于用户画像 + Skill 熟练度的自适应难度算法。

P1 完整实现：
- 四因子加权评分（掌握度/正确率/近期趋势/遗忘因子）
- 近期趋势：从 evolution_history 分析最近 N 次练习的趋势方向
- 遗忘因子：基于末次练习时间的指数衰减模型
- 上下文感知：支持考试模式/练习模式/错题重练的不同策略
- 批次估算：支持一次估算多个知识点
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.data.database import get_db_session

logger = logging.getLogger(__name__)

# 权重配置（可通过外部配置覆盖）
DEFAULT_WEIGHTS = {
    "mastery": 0.35,       # 知识点掌握度权重
    "overall": 0.20,       # 整体正确率权重
    "trend": 0.25,         # 近期趋势权重
    "time_decay": 0.15,    # 遗忘因子权重
    "difficulty_bonus": 0.05,  # 题目难度奖励
}

# 难度映射表（细化边界）
DIFFICULTY_MAP = [
    (0.90, 5, "挑战"),
    (0.75, 4, "进阶"),
    (0.55, 3, "标准"),
    (0.35, 2, "基础"),
    (0.00, 1, "入门"),
]

# 上下文策略调整
CONTEXT_ADJUSTMENTS = {
    "exam": -0.5,        # 考试模式：降低难度（确保正确率）
    "practice": 0.0,     # 练习模式：标准
    "review": 0.5,       # 复习模式：提高难度（检验掌握度）
    "error_correction": -1.0,  # 错题重练：大幅降低难度
    "challenge": 1.0,    # 挑战模式：大幅提高难度
}

# 趋势计算窗口（天数）
TREND_WINDOW_DAYS = 14
TREND_MIN_RECORDS = 3


class DifficultyEstimator:
    """
    基于用户画像 + Skill 熟练度的动态难度估算（P1 完整实现）。

    核心算法（四因子加权评分）：

        score = w1 × category_mastery
              + w2 × overall_correct_rate
              + w3 × recent_trend_score
              + w4 × memory_decay_score
              + w5 × difficulty_bonus

    score ∈ [0, 1]，映射到 1-5 分制。

    特点：
    - 近期趋势：通过 evolution_history 检测"上升/平稳/下降"趋势
    - 遗忘因子：基于遗忘曲线模型，时间越长得分越低
    - 上下文感知：考试/练习/复习等场景自动调整难度
    - 阈值保护：数据不足时降级到保守估算
    """

    def __init__(self, skill_aggregator=None, db_session_factory=None):
        self._skill_aggregator = skill_aggregator
        self._session_factory = db_session_factory or get_db_session
        self._weights = dict(DEFAULT_WEIGHTS)

    def update_weights(self, weights: Dict[str, float]) -> None:
        """动态更新权重配置（支持外部调优）。"""
        for key, val in weights.items():
            if key in self._weights:
                self._weights[key] = val
        logger.info(f"权重已更新: {self._weights}")

    async def estimate(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        profile: Optional[Dict[str, Any]] = None,
        context: str = "practice",
        skill_data: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        估算用户的推荐难度（1-5）。

        Args:
            user_id: 用户 ID
            category: 目标知识点分类
            sub_category: 子分类（用于精确匹配 skill）
            profile: 可选用户画像（避免重复查询）
            context: 上下文模式（practice/exam/review/error_correction/challenge）
            skill_data: 可选的技能数据列表（避免重复查询）

        Returns:
            int: 推荐难度 1-5
        """
        # ── 因子 1: 知识点掌握度 ──
        category_mastery = await self._get_category_mastery(
            user_id, category, sub_category, skill_data
        )

        # ── 因子 2: 整体正确率 ──
        overall_rate = self._get_overall_rate(profile)

        # ── 因子 3: 近期趋势 ──
        trend_score = await self._calculate_recent_trend(
            user_id, category, sub_category, skill_data
        )

        # ── 因子 4: 遗忘因子 ──
        time_decay = await self._calculate_time_factor(
            user_id, category, sub_category, skill_data
        )

        # ── 因子 5: 难度奖励（该知识点历史难度均值） ──
        difficulty_bonus = await self._calculate_difficulty_bonus(
            user_id, category, sub_category
        )

        # ── 加权评分 ──
        w = self._weights
        score = (
            w["mastery"] * category_mastery
            + w["overall"] * overall_rate
            + w["trend"] * trend_score
            + w["time_decay"] * time_decay
            + w["difficulty_bonus"] * difficulty_bonus
        )

        # ── 上下文调整 ──
        adjustment = CONTEXT_ADJUSTMENTS.get(context, 0.0)
        score = max(0.0, min(1.0, score + adjustment * 0.1))

        difficulty = self._score_to_difficulty(score)
        logger.info(
            f"  [难度估算] {context}模式: 掌握度={category_mastery:.2f} "
            f"正确率={overall_rate:.2f} 趋势={trend_score:.2f} "
            f"遗忘={time_decay:.2f} 奖励={difficulty_bonus:.2f} "
            f"调整={adjustment:+.1f} → 综合分={score:.2f} → 难度{difficulty}级"
        )
        print(
            f"[DIFF] 难度估算详情 | user={user_id} | category={category} | "
            f"掌握度={category_mastery:.2f}(权重35%) | "
            f"正确率={overall_rate:.2f}(权重20%) | "
            f"趋势={trend_score:.2f}(权重25%) | "
            f"遗忘={time_decay:.2f}(权重15%) | "
            f"奖励={difficulty_bonus:.2f}(权重5%) | "
            f"上下文调整={adjustment:+.1f} | "
            f"综合分={score:.3f} → 难度{difficulty}级",
            flush=True
        )
        return difficulty

    async def estimate_for_profile(
        self,
        user_id: str,
        profile: Any,
        context: str = "practice",
    ) -> int:
        """
        基于 UserProfile 对象估算整体推荐难度。
        用于更新 profile.recommended_difficulty。

        Args:
            user_id: 用户 ID
            profile: UserProfile 对象（或类似结构）
            context: 上下文模式

        Returns:
            int: 推荐难度 1-5
        """
        if not profile or profile.total_questions == 0:
            return 3  # 无数据时默认中等难度

        # 使用各项技能掌握度求加权平均
        category_scores = []

        if profile.skills:
            for skill in profile.skills:
                cat = skill.get("category_path", skill.get("skill_code", ""))
                mastery = skill.get("mastery_level", 0.0)
                attempts = skill.get("total_attempts", 1)
                category_scores.append((cat, mastery, attempts))

        if not category_scores:
            # 无技能数据：基于整体正确率估算
            cr = profile.correct_rate or 0.5
            d = self._score_to_difficulty(cr)
            return self._apply_context(d, context)

        # 加权平均（练习次数越多，权重越大）
        total_weight = sum(max(a, 1) for _, _, a in category_scores)
        weighted = sum(m * max(a, 1) for _, m, a in category_scores) / total_weight

        difficulty = self._score_to_difficulty(weighted)
        return self._apply_context(difficulty, context)

    async def estimate_batch(
        self,
        user_id: str,
        categories: List[Dict[str, str]],
        profile: Optional[Dict[str, Any]] = None,
        context: str = "practice",
    ) -> Dict[str, int]:
        """
        批次估算多个知识点的推荐难度。

        Args:
            user_id: 用户 ID
            categories: [{"category": "...", "sub_category": "..."}, ...]
            profile: 可选用户画像
            context: 上下文模式

        Returns:
            Dict[str, int]: {"category_sub": 3, ...}
        """
        results = {}
        for item in categories:
            cat = item.get("category", "")
            sub = item.get("sub_category", "")
            key = f"{cat}_{sub}" if sub else cat
            difficulty = await self.estimate(
                user_id=user_id,
                category=cat,
                sub_category=sub,
                profile=profile,
                context=context,
            )
            results[key] = difficulty
        return results

    # ── 内部方法 ──

    async def _get_category_mastery(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        skill_data: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """获取某知识点的掌握度 (0-1)。"""
        if not sub_category:
            return 0.5  # 无子分类时默认中值

        skill_code = (
            f"{category}_{sub_category}".lower().replace(" ", "_")
        )

        if skill_data:
            for s in skill_data:
                if s.get("skill_code") == skill_code:
                    return s.get("mastery_level", 0.0)

        if self._skill_aggregator:
            try:
                skills = await self._skill_aggregator.get_all_skills(user_id)
                for s in skills:
                    if s["skill_code"] == skill_code:
                        return s["mastery_level"]
            except Exception as e:
                logger.warning(f"获取掌握度失败: {e}")

        return 0.5

    async def _calculate_recent_trend(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        skill_data: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """
        计算近期学习趋势 (0-1)。

        从 evolution_history 分析最近 N 次练习的正确率趋势：
        - 上升趋势 → 高分 (0.6-1.0)
        - 平稳趋势 → 中分 (0.4-0.6)
        - 下降趋势 → 低分 (0.0-0.4)
        - 无数据 → 默认 0.5
        """
        history = None
        if skill_data:
            for s in skill_data:
                if s.get("skill_code", "").startswith(
                    f"{category}_{sub_category}".lower().replace(" ", "_")
                ):
                    history = s.get("evolution_history", [])
                    break

        if not history and self._skill_aggregator and sub_category:
            try:
                skills = await self._skill_aggregator.get_all_skills(user_id)
                skill_code = (
                    f"{category}_{sub_category}".lower().replace(" ", "_")
                )
                for s in skills:
                    if s["skill_code"] == skill_code:
                        history = s.get("evolution_history", [])
                        break
            except Exception:
                pass

        if not history or len(history) < TREND_MIN_RECORDS:
            return 0.5  # 数据不足，中性

        # 提取最近 TREND_MIN_RECORDS 个记录点的掌握度
        recent = history[-TREND_MIN_RECORDS:]
        mastery_values = [h.get("mastery", 0.0) for h in recent]

        if len(mastery_values) < 2:
            return mastery_values[0] if mastery_values else 0.5

        # 线性回归：斜率 > 0 表示上升趋势
        n = len(mastery_values)
        x_mean = (n - 1) / 2
        y_mean = sum(mastery_values) / n
        numerator = sum(i * m for i, m in enumerate(mastery_values)) - n * x_mean * y_mean
        denominator = sum(i * i for i in range(n)) - n * x_mean * x_mean

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        # 将斜率映射到 [0, 1]
        # 斜率为 0 时 = 0.5，正斜率趋于 1.0，负斜率趋于 0.0
        trend_score = 0.5 + (slope * 10.0)
        trend_score = max(0.0, min(1.0, trend_score))

        logger.debug(
            f"趋势计算: slope={slope:.4f} values={mastery_values} "
            f"→ score={trend_score:.2f}"
        )
        return trend_score

    async def _calculate_time_factor(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        skill_data: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """
        计算遗忘因子 (0-1)。

        基于遗忘曲线模型：
        - 最近 1 天内练习过 → 0.9-1.0（几乎未遗忘）
        - 最近 7 天内练习过 → 0.6-0.9
        - 最近 30 天内练习过 → 0.3-0.6
        - 超过 30 天 → 0.0-0.3

        使用指数衰减: score = e^(-days / half_life)
        half_life = 14 天
        """
        last_practiced = None

        if skill_data:
            for s in skill_data:
                if s.get("skill_code", "").startswith(
                    f"{category}_{sub_category}".lower().replace(" ", "_")
                ):
                    lp = s.get("last_practiced")
                    if lp:
                        try:
                            last_practiced = datetime.fromisoformat(
                                lp.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass
                    break

        if not last_practiced and self._skill_aggregator and sub_category:
            try:
                skills = await self._skill_aggregator.get_all_skills(user_id)
                skill_code = (
                    f"{category}_{sub_category}".lower().replace(" ", "_")
                )
                for s in skills:
                    if s["skill_code"] == skill_code:
                        lp = s.get("last_practiced")
                        if lp:
                            try:
                                last_practiced = datetime.fromisoformat(
                                    lp.replace("Z", "+00:00")
                                )
                            except (ValueError, AttributeError):
                                pass
                        break
            except Exception:
                pass

        if not last_practiced:
            return 0.5  # 无数据，中性

        now = datetime.now(timezone.utc)
        if last_practiced.tzinfo is None:
            last_practiced = last_practiced.replace(tzinfo=timezone.utc)

        days_elapsed = max(0.0, (now - last_practiced).total_seconds() / 86400.0)

        # 指数衰减模型，半衰期 14 天
        half_life = 14.0
        decay_score = math.exp(-days_elapsed / half_life)

        logger.debug(
            f"遗忘因子: days={days_elapsed:.1f} decay={decay_score:.2f}"
        )
        return decay_score

    async def _calculate_difficulty_bonus(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
    ) -> float:
        """
        计算难度奖励因子 (0-1)。

        基于该知识点历史练习的平均难度：
        - 一直练习高难度题 → 高分（说明有能力应对高难度）
        - 一直练习低难度题 → 低分（说明尚在基础阶段）
        - 无数据 → 默认 0.5
        """
        if not self._skill_aggregator or not sub_category:
            return 0.5

        try:
            skills = await self._skill_aggregator.get_all_skills(user_id)
            skill_code = (
                f"{category}_{sub_category}".lower().replace(" ", "_")
            )
            for s in skills:
                if s["skill_code"] == skill_code:
                    total = s.get("total_attempts", 0)
                    correct = s.get("correct_count", 0)
                    if total >= 3:
                        rate = correct / total
                        # 高正确率 × 高练习量 → 可提高难度
                        bonus = 0.5 + (rate - 0.5) * min(total / 10.0, 1.0)
                        return max(0.0, min(1.0, bonus))
        except Exception:
            pass

        return 0.5

    @staticmethod
    def _get_overall_rate(profile: Optional[Dict[str, Any]]) -> float:
        """从画像中提取整体正确率。"""
        if not profile:
            return 0.5
        return profile.get("correct_rate", 0.5)

    @staticmethod
    def _score_to_difficulty(score: float) -> int:
        """score ∈ [0,1] → difficulty ∈ [1,5]。"""
        score = max(0.0, min(1.0, score))
        for threshold, difficulty, _ in DIFFICULTY_MAP:
            if score >= threshold:
                return difficulty
        return 1

    @staticmethod
    def _apply_context(difficulty: int, context: str) -> int:
        """对难度进行上下文微调。"""
        adjustment = CONTEXT_ADJUSTMENTS.get(context, 0.0)
        adjusted = difficulty + adjustment
        return max(1, min(5, int(round(adjusted))))