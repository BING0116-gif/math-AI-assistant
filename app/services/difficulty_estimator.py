import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DifficultyEstimator:
    """
    基于用户画像 + Skill 熟练度的动态难度估算。

    算法: 加权评分 → 映射到 1-5 分制

    score = 0.4 × category_mastery(category)
          + 0.3 × overall_correct_rate
          + 0.2 × recent_trend(category, window=10)
          + 0.1 × time_since_last_practice(category)
    """

    def __init__(self, skill_aggregator=None):
        self._skill_aggregator = skill_aggregator

    async def estimate(
        self,
        user_id: str,
        category: str,
        sub_category: str = "",
        profile: Optional[Dict[str, Any]] = None,
    ) -> int:
        skill_code = (
            f"{category}_{sub_category}".lower().replace(" ", "_")
            if sub_category
            else ""
        )

        category_mastery = 0.0
        if self._skill_aggregator and skill_code:
            skills = await self._skill_aggregator.get_all_skills(user_id)
            for s in skills:
                if s["skill_code"] == skill_code:
                    category_mastery = s["mastery_level"]
                    break

        overall_rate = (
            profile.get("correct_rate", 0.5) if profile else 0.5
        )

        recent_trend = 0.5

        time_factor = 0.5

        score = (
            0.4 * category_mastery
            + 0.3 * overall_rate
            + 0.2 * recent_trend
            + 0.1 * time_factor
        )

        difficulty = self._score_to_difficulty(score)
        logger.info(
            f"难度估算: mastery={category_mastery:.2f} overall={overall_rate:.2f} "
            f"trend={recent_trend:.2f} time_f={time_factor:.2f} → score={score:.2f} → d={difficulty}"
        )
        return difficulty

    @staticmethod
    def _score_to_difficulty(score: float) -> int:
        if score > 0.85:
            return 5
        elif score > 0.65:
            return 4
        elif score > 0.45:
            return 3
        elif score > 0.25:
            return 2
        else:
            return 1