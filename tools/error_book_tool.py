"""
错题本分析工具 — Agent 调用此工具分析用户的错题记录。

触发场景: 用户说"看看我的错题"、"分析一下我经常错的知识点"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class ErrorBookTool(BaseTool):
    name = "error_book_analysis"
    description = "分析用户的错题记录，找出薄弱知识点和错误模式，提供针对性建议"
    version = "1.0.0"
    capabilities = [ToolCapability.ERROR_BOOK_MANAGEMENT, ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "分析最近N道错题，默认10"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.error_book_sync import ErrorBookSkillSyncService

            user_id = input_data.context.get("user_id", "anonymous")
            service = ErrorBookSkillSyncService()
            summary = await service.get_skill_impact_summary(user_id)

            if summary["total_error_records"] == 0:
                return ToolOutput(success=True, result="暂无错题记录，继续保持！")

            lines = [
                f"## 错题分析\n",
                f"- 总错题数: {summary['total_error_records']}",
                f"- 已掌握: {summary['mastered_errors']}",
                f"- 待攻克: {summary['unmastered_errors']}",
            ]

            if summary.get("weak_categories"):
                lines.append(f"\n### 薄弱知识点 Top5")
                for wc in summary["weak_categories"]:
                    lines.append(f"- {wc['category']}: {wc['count']}道错题")

            lines.append(f"\n建议：优先攻克数量最多的薄弱知识点，每道错题至少重新做2遍。")

            return ToolOutput(success=True, result="\n".join(lines), data=summary)
        except Exception as e:
            return ToolOutput(success=False, error=f"错题分析失败: {str(e)}")