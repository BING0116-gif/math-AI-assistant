"""
题目讲解工具 — Agent 调用此工具对某道数学题目进行详细讲解。

触发场景: 用户说"讲一下这道题"、"这道题为什么选C"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class ExplainTool(BaseTool):
    name = "explain_question"
    description = "对某道数学题目进行详细讲解，包括知识点回顾、解题步骤、常见错误提示"
    version = "1.0.0"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL, ToolCapability.VERIFICATION]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string", "description": "题目ID（可选）"},
                    "question_content": {"type": "string", "description": "题目内容（如果没有ID）"},
                    "user_answer": {"type": "string", "description": "用户的答案（可选）"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.data.database import get_db_session
            from app.data.models import Question
            from app.services.llm_service import get_llm_service

            params = input_data.parameters or {}
            question_id = params.get("question_id")
            question_content = params.get("question_content", input_data.query)
            user_answer = params.get("user_answer")

            # 如果有ID，从数据库获取完整题目
            if question_id:
                async with get_db_session() as db:
                    q = await db.get(Question, question_id)
                    if q:
                        question_content = q.content
                        correct_answer = q.answer
                        analysis = q.analysis or ""
                        category = q.category
                    else:
                        return ToolOutput(success=False, error=f"未找到题目: {question_id}")
            else:
                correct_answer = "未知"
                analysis = ""
                category = "数学"

            llm = get_llm_service()
            system_prompt = (
                "你是一位数学老师。请对以下题目进行详细讲解，包括：\n"
                "1. 考察的知识点\n2. 解题思路和步骤\n3. 常见错误提醒\n"
                "如果用户给出了答案，请判断对错并分析错误原因。"
            )
            prompt = (
                f"题目: {question_content}\n"
                f"知识点: {category}\n"
                f"正确答案: {correct_answer}\n"
                f"题库解析: {analysis}\n"
            )
            if user_answer:
                prompt += f"用户答案: {user_answer}\n请判断对错并分析。"

            response = await llm.generate_with_math_model(prompt=prompt, system_prompt=system_prompt)
            return ToolOutput(success=True, result=response.content)
        except Exception as e:
            return ToolOutput(success=False, error=f"讲解失败: {str(e)}")