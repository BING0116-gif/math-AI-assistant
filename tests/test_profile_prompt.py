from types import SimpleNamespace

from agent_core.agent import MathAgent
from agent_core.profile_prompt import format_skill_profile_for_llm


def _profile(**overrides):
    values = {
        "correct_rate": 0.72,
        "weak_points": [],
        "strong_points": [],
        "skills": [],
        "recommended_difficulty": 3,
        "error_patterns": [],
        "cognitive_style": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_legacy_agent_formatter_delegates_without_output_drift():
    profile = _profile(
        weak_points=[{"category": "极限", "mastery": 0.2}],
        strong_points=["导数"],
        error_patterns=[{"pattern": "漏写定义域"}],
        cognitive_style={"style_hint": "先看图像"},
    )

    direct = format_skill_profile_for_llm(profile)
    assert MathAgent._format_skill_profile_for_llm(profile) == direct
    assert "薄弱知识点: 极限(20%)" in direct
    assert "已掌握: 导数" in direct
    assert "常见易错: 漏写定义域" in direct
    assert "学习偏好: 先看图像" in direct


def test_formatter_deduplicates_weak_skills_and_bounds_items():
    profile = _profile(
        weak_points=[{"category": "极限", "mastery": 0.2}],
        skills=[
            {"skill_code": "极限", "mastery_level": 0.2, "status": "learning"},
            {"skill_code": "积分", "mastery_level": 0.3, "status": "learning"},
        ],
    )

    result = format_skill_profile_for_llm(profile)
    assert result.count("极限(20%)") == 1
    assert "积分(30%)" in result
