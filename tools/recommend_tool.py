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
    description = (
        "【出题/推荐题目的唯一工具】当用户要求出题、推荐题目、练习、测试、挑战时，"
        "必须调用此工具从题库中检索真实题目。禁止自己编造题目。"
        "支持指定知识点（如'导数'、'极限'）、数量和场景模式。"
    )
    version = "1.3.0"
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
        # ===== 强制输出：验证此方法是否被调用 =====
        print(f"\n{'='*60}")
        print(f"[RECOMMEND_TOOL] >>>>> 推荐工具被触发！<<<<")
        print(f"[RECOMMEND_TOOL] user_id={input_data.context.get('user_id', '?')}")
        print(f"{'='*60}\n", flush=True)
        # ============================================

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
            print(f"[RECOMMEND_TOOL] 三路检索完成 | SQL={sql_count} + 向量={vec_count} → {final_count}题 | {elapsed_ms:.0f}ms", flush=True)

            # ── 中文日志：每道题的来源追踪 ──
            for i, q in enumerate(result.questions):
                qid = q.get('id', '?')
                src = q.get('source', '?')
                diff = q.get('difficulty', '?')
                content_preview = (q.get('content') or '')[:80].replace('\n', ' ')
                logger.info(f"  第{i+1}题 ID={qid} 来源={src} 难度={diff} 内容={content_preview}")
                print(f"[RECOMMEND_TOOL]   第{i+1}题 | ID={qid} | 来源={src} | 难度={diff}", flush=True)

            # ── 构建返回给LLM的文本（含来源标注，强制原样展示）──
            question_lines = []
            for i, q in enumerate(result.questions):
                content = q.get('content', '')
                qid = q.get('id', '?')
                src = q.get('source', '?')
                diff = q.get('difficulty', '?')
                # 每道题附带来源信息，用户可交叉验证
                question_lines.append(
                    f"**第{i+1}题** (ID: {qid} | 来源: {src} | 难度: {diff}级):\n{content}"
                )

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
                    ai_advice = "\n\n---\n\n**[AI学习建议]**（以下为补充分析，非题目内容）:\n" + "\n".join(parts)
                    logger.info(f"【推荐工具】AI分析已生成: {list(ai.keys())}")

            # 返回给LLM的文本 — 格式化为"引用块"，明确告诉LLM这是不可修改的内容
            result_text = f"""<<RAG推荐结果_开始>>
以下是系统从题库中检索出的{final_count}道{category}题目（已通过SQL精确匹配+向量语义搜索+知识图谱融合排序）：

{''.join(question_lines)}
{ai_advice}
<<RAG推荐结果_结束>>

【输出要求】你必须将 <<RAG推荐结果_开始>> 和 <<RAG推荐结果_结束>> 之间的内容逐字原样展示给用户，不得修改、省略或替换其中的任何题目。"""

            # 记录原始返回文本的hash，用于后续对比LLM实际输出
            import hashlib
            _result_hash = hashlib.md5(result_text.encode()).hexdigest()[:8]
            print(f"[RECOMMEND_TOOL] 返回LLM的原文hash={_result_hash} | 长度={len(result_text)}字符", flush=True)

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
