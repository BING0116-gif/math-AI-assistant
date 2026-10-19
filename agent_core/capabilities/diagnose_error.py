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
        # review 只有在用户明确要求诊断，或上下文确实带有学生推导时才
        # 进入诊错链路。普通数学题即使携带 review 模式，也应走 solve，
        # 否则会暴露错题分析工具并错过 math_solver。
        if self._DIAGNOSIS_MARKERS.search(str(user_input or "")):
            return True
        if context.get("tutor_mode") != "review":
            return False
        return any(
            context.get(key)
            for key in ("student_work", "student_answer", "student_solution", "submitted_work")
        )
