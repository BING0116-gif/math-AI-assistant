"""
题库搜索工具 — Agent 调用此工具在题库中搜索符合条件的题目。

触发场景: 用户说"找一些关于微积分基本定理的题目"、"有没有不定积分的计算题"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class SearchTool(BaseTool):
    name = "search_questions"
    description = "在题库中搜索符合条件的数学题目，支持按知识点、难度、关键词搜索"
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
                    "query": {"type": "string", "description": "搜索关键词或描述"},
                    "category": {"type": "string", "description": "知识点分类"},
                    "difficulty": {"type": "integer", "description": "难度等级 1-5"},
                    "limit": {"type": "integer", "description": "返回数量，默认5"},
                },
                "required": ["query"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.vector_store import get_vector_store

            params = input_data.parameters or {}
            query = params.get("query", input_data.query)
            category = params.get("category")
            difficulty = params.get("difficulty")
            limit = int(params.get("limit", 5))

            vs = await get_vector_store()
            difficulty_range = None
            if difficulty:
                difficulty_range = (difficulty, difficulty)

            results = await vs.hybrid_search(
                query=query, category_filter=category,
                difficulty_range=difficulty_range, n_results=limit,
            )

            if not results:
                return ToolOutput(success=True, result="未找到匹配的题目。")

            output = "\n".join(
                f"{i+1}. [{r.id}] {r.content[:100]}... (难度:{r.metadata.get('difficulty', '?')}, 相似度:{r.score:.2f})"
                for i, r in enumerate(results)
            )
            return ToolOutput(
                success=True,
                result=f"找到 {len(results)} 道相关题目：\n\n{output}",
                data={"results": [{"id": r.id, "content": r.content, "score": r.score} for r in results]},
            )
        except Exception as e:
            return ToolOutput(success=False, error=f"搜索失败: {str(e)}")