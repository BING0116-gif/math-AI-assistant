"""学生步骤比对与错误诊断 Capability。"""

from __future__ import annotations

import re
from typing import Any, Mapping

from agent_core.capabilities.base import Capability, CapabilityManifest


class DiagnoseErrorCapability(Capability):
    """优先让模型检查学生已有过程，而非重新代做整题。"""

    manifest = CapabilityManifest(
        name="diagnose_error",
        supported_modes=("tutor_free", "guided", "review"),
        stages=("collect_student_work", "compare_steps", "verify", "feedback"),
        allowed_tools=frozenset({
            "vision_tool", "search_questions", "skill_profile", "ask_student",
            "math_verify", "math_visualize", "error_book_analysis",
        }),
        strategy_policy="existing_complexity_strategy",
    )

    _DIAGNOSIS_MARKERS = re.compile(
        r"(?:哪里错|哪[一]?步错|帮我检查|检查(?:我的|这[个些])?(?:步骤|推导|过程|思路)|"
        r"批改|诊断|错误原因|为什么错|我(?:算|写|推|做)到|我的(?:步骤|推导|答案))",
        re.IGNORECASE,
    )

    def matches(self, user_input: str, context: Mapping[str, Any]) -> bool:
        # review 是明确的“检查学生工作”模式；其它模式要求出现诊断意图，避免
        # 将普通求解错误路由为诊断。
        if context.get("tutor_mode") == "review":
            return True
        return bool(self._DIAGNOSIS_MARKERS.search(str(user_input or "")))
