"""Pure prompt formatting helpers for learner profile snapshots."""

from __future__ import annotations

from typing import Any


def format_skill_profile_for_llm(profile: Any) -> str:
    """Format a profile snapshot as compact, actionable LLM guidance."""

    lines = ["【用户学习档案】(基于历史学习数据分析)"]

    correct_rate = profile.correct_rate or 0
    if correct_rate >= 0.85:
        level, level_hint = "优秀", "可挑战高难度，引入竞赛/拓展内容"
    elif correct_rate >= 0.7:
        level, level_hint = "良好", "保持当前节奏，适当增加深度"
    elif correct_rate >= 0.5:
        level, level_hint = "中等", "注重基础巩固，循序渐进"
    elif correct_rate >= 0.3:
        level, level_hint = "初学", "从基础概念讲起，多用例子"
    else:
        level, level_hint = "入门", "用最简单的语言，一步步引导"
    lines.append(f"- 当前水平: {level} (正确率 {correct_rate:.0%}) → {level_hint}")

    weak_skills = []
    for weak_point in (profile.weak_points or [])[:4]:
        weak_skills.append(
            f"{weak_point.get('category', '')}({weak_point.get('mastery', 0):.0%})"
        )
    for skill in sorted(
        profile.skills or [], key=lambda item: item.get("mastery_level", 0)
    )[:4]:
        mastery = skill.get("mastery_level", 0)
        if mastery < 0.35 and skill.get("status", "") != "mastered":
            name = skill.get("skill_code", skill.get("display_name", ""))
            weak_skills.append(f"{name}({mastery:.0%})")
    if weak_skills:
        unique_weak = list(dict.fromkeys(weak_skills))[:5]
        lines.append(
            f"- 薄弱知识点: {', '.join(unique_weak)} → 请重点讲解基础概念，多给示例和类比"
        )

    strong_skills = list(profile.strong_points or [])[:3]
    for skill in sorted(
        profile.skills or [],
        key=lambda item: item.get("mastery_level", 0),
        reverse=True,
    )[:3]:
        if skill.get("status") == "mastered":
            name = skill.get("skill_code", skill.get("display_name", ""))
            if name not in strong_skills:
                strong_skills.append(name)
    if strong_skills:
        lines.append(
            f"- 已掌握: {', '.join(strong_skills[:3])} → 可适当提高深度，引入关联知识"
        )

    lines.append(f"- 推荐答题难度: T{int(profile.recommended_difficulty or 3)}")

    error_patterns = (
        profile.error_patterns
        if isinstance(profile.error_patterns, list)
        else getattr(profile, "error_pattern_list", None) or []
    )
    patterns = [
        item.get("pattern", "") for item in error_patterns[:3] if item.get("pattern")
    ]
    if patterns:
        lines.append(f"- 常见易错: {', '.join(patterns)} → 回答时主动提醒这些错误")

    style_hint = (profile.cognitive_style or {}).get("style_hint", "")
    if style_hint:
        lines.append(f"- 学习偏好: {style_hint}")

    return "\n".join(lines)


__all__ = ["format_skill_profile_for_llm"]
