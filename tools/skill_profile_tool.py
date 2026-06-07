"""
技能画像工具 — Agent 调用此工具查询用户的学习状态。

触发场景: 用户说"我的薄弱点是什么"、"导数掌握得怎么样"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class SkillProfileTool(BaseTool):
    name = "skill_profile"
    description = "查询用户技能画像，包括各知识点掌握度、薄弱点、推荐难度、已掌握技能和下一步学习建议"
    version = "1.0.0"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "可选，查询特定知识点的掌握情况"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from agent_core.memory_persistence import MemoryPersistenceFacade
            from app.services.skill_aggregator import SkillAggregator
            from app.services.difficulty_estimator import DifficultyEstimator

            user_id = input_data.context.get("user_id", "anonymous")
            facade = MemoryPersistenceFacade()
            profile = await facade.get_profile(user_id)

            skills = await SkillAggregator().get_all_skills(user_id)
            mastered = [s for s in skills if s["status"] == "mastered"]
            weak = [s for s in skills if s["status"] in ("novice", "learning")]

            result_lines = [
                f"## 学习画像\n",
                f"- 正确率: {profile.correct_rate:.0%}",
                f"- 推荐难度: T{profile.recommended_difficulty}",
                f"- 已掌握: {len(mastered)}个知识点",
                f"- 薄弱点: {len(weak)}个知识点",
            ]

            if profile.weak_points:
                result_lines.append(f"\n### 薄弱知识点")
                for wp in profile.weak_points[:5]:
                    result_lines.append(f"- {wp.get('category', '')} (掌握度: {wp.get('mastery', 0):.0%})")

            if mastered:
                result_lines.append(f"\n### 已掌握")
                result_lines.append(", ".join(s["skill_code"] for s in mastered[:5]))

            return ToolOutput(
                success=True,
                result="\n".join(result_lines),
                data={"skills": skills, "profile": profile.to_dict()},
            )
        except Exception as e:
            return ToolOutput(success=False, error=f"获取技能画像失败: {str(e)}")