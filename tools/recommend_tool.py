"""
智能推荐工具 — Agent 调用此工具获取个性化题目推荐。

触发场景: 用户说"推荐几道导数题"、"给我来几道极限题练练"
"""

from __future__ import annotations

import logging
import time
from typing import Any

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability

logger = logging.getLogger(__name__)


class RecommendTool(BaseTool):
    name = "recommend_questions"
    description = "根据用户的学习情况推荐个性化数学题目，支持指定知识点、数量和场景"
    version = "1.2.0"
    capabilities = [ToolCapability.PRACTICE_GENERATION, ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "目标知识点分类，如'导数'、'极限'、'积分'"},
                    "count": {"type": "integer", "description": "推荐数量，默认5"},
                    "context": {"type": "string", "description": "practice/exam/review/error_correction/challenge"},
                },
                "required": ["category"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.rag_recommender import get_rag_recommender, RecommendationRequest

            params = input_data.parameters or {}
            category = params.get("category", input_data.query or "")
            count = int(params.get("count", 5))
            context = params.get("context", "practice")
            user_id = input_data.context.get("user_id", "anonymous")

            # ── 中文日志：开始推荐 ──
            logger.info(f"【推荐工具】开始为用户「{user_id}」推荐 {count} 道「{category}」题目 (模式={context})")

            start = time.time()
            recommender = await get_rag_recommender()
            result = await recommender.recommend(RecommendationRequest(
                user_id=user_id,
                target_category=category,
                count=count,
                context=context,
            ))
            elapsed_ms = (time.time() - start) * 1000

            meta = result.meta or {}

            # ── 中文日志：检索结果统计 ──
            sql_count = meta.get('sql_result_count', '?')
            vec_count = meta.get('vector_result_count', '?')
            final_count = len(result.questions)
            method = meta.get('retrieval_method', '?')
            logger.info(
                f"【推荐工具】三路检索完成 | "
                f"SQL精确={sql_count}题 + 向量语义={vec_count}题 → 融合排序后取{final_count}题 | "
                f"耗时{elapsed_ms:.0f}ms"
            )

            # ── 中文日志：每道题的来源追踪 ──
            for i, q in enumerate(result.questions):
                qid = q.get('id', '?')
                src = q.get('source', '?')
                diff = q.get('difficulty', '?')
                content_preview = (q.get('content') or '')[:80].replace('\n', ' ')
                logger.info(f"  第{i+1}题 ID={qid} 来源={src} 难度={diff} 内容={content_preview}")

            # ── 构建返回给LLM的文本（干净格式，不含技术细节）──
            question_lines = []
            for i, q in enumerate(result.questions):
                content = q.get('content', '')
                question_lines.append(f"**第{i+1}题:**\n{content}")

            ai_advice = ""
            if result.ai_analysis:
                ai = result.ai_analysis
                parts = []
                if ai.get('assessment'):
                    parts.append(f"- 能力评估: {ai['assessment']}")
                if ai.get('recommendation_reason'):
                    parts.append(f"- 推荐理由: {ai['recommendation_reason']}")
                if ai.get('learning_advice'):
                    parts.append(f"- 学习建议: {ai['learning_advice']}")
                if parts:
                    ai_advice = "\n\n**学习建议:**\n" + "\n".join(parts)
                    logger.info(f"【推荐工具】AI分析已生成: {list(ai.keys())}")

            # 返回给LLM的文本——简洁明了，让LLM直接展示给用户
            result_text = f"""为你推荐以下{final_count}道{category}题目：

{''.join(question_lines)}
{ai_advice}

请将以上题目完整展示给用户，保持公式和文字原样。"""

            logger.info(f"【推荐工具】推荐完成，共{final_count}题已返回给Agent")
            return ToolOutput(
                success=True,
                result=result_text,
                data={
                    "questions": result.questions,
                    "ai_analysis": result.ai_analysis,
                    "meta": meta,
                    "user_id": user_id,
                },
            )
        except Exception as e:
            logger.error(f"【推荐工具】失败: {e}", exc_info=True)
            return ToolOutput(success=False, error=f"推荐失败: {str(e)}")
