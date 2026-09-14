"""通用数学求解 Capability。"""

from __future__ import annotations

from typing import Any, Mapping

from agent_core.capabilities.base import Capability, CapabilityManifest


class SolveCapability(Capability):
    """默认任务：将完整求解交给既有的复杂度/策略选择链路。"""

    manifest = CapabilityManifest(
        name="solve",
        supported_modes=("tutor_free", "hint_only", "guided", "review"),
        stages=("understand", "plan", "solve", "respond"),
        allowed_tools=frozenset({
            "vision_tool", "search_questions", "recommend_questions",
            "skill_profile", "ask_student", "math_verify", "math_visualize", "math_animate",
            "explain_question",
        }),
        # 现有仓库当前提供 ReAct；策略选择仍完全由 MathAgent 的既有链路负责，
        # 后续接入 Planned 时无需改变 Capability 接口。
        strategy_policy="existing_complexity_strategy",
    )

    def matches(self, user_input: str, context: Mapping[str, Any]) -> bool:
        return True
