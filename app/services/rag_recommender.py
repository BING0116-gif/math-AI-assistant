"""
RAG 智能推荐引擎 — 整合所有组件，实现自适应题目推荐。

6步工作流：
1. 获取用户画像 + 技能数据 + 近期练习历史
2. 确定目标知识点（指定 or 自动推断薄弱点）
3. DifficultyEstimator 估算推荐难度
4. 三路并行检索（SQL + 向量 + 知识图谱）
5. 结果融合、去重、排序
6. LLM 生成个性化推荐理由
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Question, LearningRecord
from app.services.difficulty_estimator import DifficultyEstimator
from app.services.llm_service import LLMService, get_llm_service
from app.services.vector_store import VectorStoreManager, get_vector_store
from app.services.skill_aggregator import SkillAggregator

logger = logging.getLogger(__name__)


@dataclass
class RecommendationRequest:
    user_id: str
    target_category: str = ""
    count: int = 5
    context: str = "practice"
    exclude_ids: List[str] = field(default_factory=list)
    request_id: str = ""


@dataclass
class RecommendationResult:
    questions: List[Dict[str, Any]]
    ai_analysis: Dict[str, Any]
    meta: Dict[str, Any]
    request_id: str = ""
    generated_at: str = ""
    processing_time_ms: float = 0.0


class RAGRecommender:
    def __init__(
        self,
        db_session_factory=None,
        vector_store: Optional[VectorStoreManager] = None,
        llm_service: Optional[LLMService] = None,
        difficulty_estimator: Optional[DifficultyEstimator] = None,
        skill_aggregator: Optional[SkillAggregator] = None,
    ):
        self._session_factory = db_session_factory or get_db_session
        self._vector_store = vector_store
        self._llm = llm_service
        self._difficulty_estimator = difficulty_estimator or DifficultyEstimator()
        self._skill_aggregator = skill_aggregator or SkillAggregator()
        self.enable_rag = settings.RAG_ENABLED
        self.enable_ai_explanation = settings.RAG_ENABLE_AI_EXPLANATION
        self.enable_vector_search = settings.RAG_ENABLE_VECTOR_SEARCH
        self.hybrid_top_k = settings.RAG_HYBRID_SEARCH_TOP_K

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        start_time = time.time()
        print(f"\n{'='*60}", flush=True)
        print(f"[RAG] ====== 推荐引擎启动 ======", flush=True)
        print(f"[RAG] 用户={request.user_id} | 目标分类={request.target_category or '自动'} | 模式={request.context}", flush=True)
        logger.info(f"━━━ 推荐引擎启动 ━━━ 用户={request.user_id} 目标分类={request.target_category or '自动'} 模式={request.context}")

        try:
            # ── 第1步：获取用户画像 ──
            user_profile = await self._get_user_profile(request.user_id)
            user_skills = await self._get_user_skills_dict(request.user_id)
            recently_done = await self._get_recently_done_ids(request.user_id)

            correct_rate = user_profile.get("correct_rate", 0.5)
            total_q = user_profile.get("total_questions", 0)
            print(f"[RAG] [第1步-用户画像] 正确率={correct_rate:.0%} | 总答题数={total_q} | 薄弱点={len(user_skills)}个技能", flush=True)
            logger.info(f"  [第1步-用户画像] 正确率={correct_rate:.0%} 总答题数={total_q} 薄弱点={len(user_skills)}个技能")

            # ── 第2步：确定目标分类和难度 ──
            target_category, weak_points = await self._determine_target(
                request.target_category, user_skills, user_profile
            )

            recommended_difficulty = await self._difficulty_estimator.estimate(
                user_id=request.user_id, category=target_category,
                context=request.context, profile=user_profile,
            )
            # 同时传入user_skills让难度估算器能获取子分类级别的掌握度
            if user_skills:
                # 取第一个技能的sub_category（如果有）
                first_skill = next(iter(user_skills.values()), {})
                sub_cat = first_skill.get("sub_category", "") or first_skill.get("skill_code", "").replace(f"{target_category}_", "")
                if sub_cat and sub_cat != target_category.lower():
                    # 用带sub_category的方式重新估算（更精确）
                    recommended_difficulty_refined = await self._difficulty_estimator.estimate(
                        user_id=request.user_id, category=target_category,
                        sub_category=sub_cat, context=request.context,
                        profile=user_profile, skill_data=list(user_skills.values()),
                    )
                    if recommended_difficulty != recommended_difficulty_refined:
                        print(f"[RAG] 难度修正: {recommended_difficulty} → {recommended_difficulty_refined} (基于skill数据)", flush=True)
                        recommended_difficulty = recommended_difficulty_refined

            logger.info(f"  [第2步-目标确定] 分类={target_category} 推荐难度={recommended_difficulty}/5 薄弱点={weak_points}")
            print(f"[RAG] [第2步-目标确定] 分类={target_category} | 推荐难度={recommended_difficulty}/5 | 薄弱点={weak_points} | skill数量={len(user_skills)}", flush=True)

            all_exclude = list(set(request.exclude_ids + recently_done))
            if all_exclude:
                logger.info(f"  [排除] 近30天已练{len(all_exclude)}道题，将自动过滤")

            # ── 第3步：三路并行检索（SQL + 向量 + 知识图谱）──
            sql_task = self._sql_retrieval(target_category, recommended_difficulty, all_exclude, request.count)
            vector_task = self._vector_retrieval(target_category, recommended_difficulty, request.count * 2) if (self.enable_rag and self.enable_vector_search and self._vector_store) else asyncio.sleep(0)
            kg_task = self._kg_analysis(target_category, user_skills)

            sql_results, vector_results, kg_suggestions = await asyncio.gather(
                sql_task, vector_task, kg_task,
            )
            if not isinstance(vector_results, list):
                vector_results = []
            if not isinstance(kg_suggestions, list):
                kg_suggestions = []

            logger.info(f"  [第3步-三路检索] SQL精确={len(sql_results)}题 | 向量语义={len(vector_results)}题 | 知识图谱={len(kg_suggestions)}个建议")
            print(f"[RAG] [第3步-三路检索] SQL精确={len(sql_results)}题 | 向量语义={len(vector_results)}题 | 知识图谱={len(kg_suggestions)}个建议", flush=True)

            # ── 第4步：融合排序 ──
            final_questions = await self._fuse_and_rank(
                sql_results=sql_results, vector_results=vector_results,
                kg_suggestions=kg_suggestions, target_count=request.count,
                difficulty=recommended_difficulty,
            )
            logger.info(f"  [第4步-融合排序] 融合后取前{len(final_questions)}题")
            print(f"[RAG] [第4步-融合排序] 融合后取前{len(final_questions)}题", flush=True)

            # ── 第5步：AI生成个性化分析（可选）──
            ai_analysis = {}
            if self.enable_ai_explanation and self._llm and final_questions:
                try:
                    ai_analysis = await asyncio.wait_for(
                        self._generate_ai_analysis(
                            user_profile=user_profile, questions=final_questions,
                            difficulty=recommended_difficulty, weak_points=weak_points,
                            target_category=target_category,
                        ),
                        timeout=15.0,
                    )
                    logger.info(f"  [第5步-AI分析] 已生成（能力评估+推荐理由+学习建议）")
                    print(f"[RAG] [第5步-AI分析] 已生成（能力评估+推荐理由+学习建议）", flush=True)
                except asyncio.TimeoutError:
                    logger.warning("  [第5步-AI分析] 超时(>15s)，跳过AI分析")
                    correct_rate = user_profile.get("correct_rate", 0.5)
                    ai_analysis = self._default_analysis(correct_rate, target_category, len(final_questions), recommended_difficulty)

            total_time = (time.time() - start_time) * 1000
            result = RecommendationResult(
                questions=[self._question_to_dict(q) for q in final_questions],
                ai_analysis=ai_analysis,
                meta={
                    "target_category": target_category,
                    "recommended_difficulty": recommended_difficulty,
                    "weak_points": weak_points,
                    "context": request.context,
                    "retrieval_method": "hybrid" if self.enable_rag else "sql_only",
                    "sql_result_count": len(sql_results),
                    "vector_result_count": len(vector_results),
                    "final_count": len(final_questions),
                    "total_ms": total_time,
                },
                request_id=request.request_id or f"rec_{int(time.time()*1000)}",
                generated_at=datetime.now(timezone.utc).isoformat(),
                processing_time_ms=total_time,
            )
            logger.info(f"━━━ 推荐完成 ━━━ 共{len(result.questions)}题 总耗时{total_time:.0f}ms ━━━")
            print(f"[RAG] ====== 推荐完成 ====== 共{len(result.questions)}题 | 总耗时{total_time:.0f}ms", flush=True)
            print(f"{'='*60}\n", flush=True)
            return result
        except Exception as e:
            logger.error(f"━━━ 推荐异常: {e} ━━━", exc_info=True)
            fallback = await self._get_fallback_recommendation(request)
            fallback.processing_time_ms = (time.time() - start_time) * 1000
            fallback.meta["error"] = str(e)
            return fallback

    async def _get_user_profile(self, user_id: str) -> Dict[str, Any]:
        from agent_core.memory_persistence import MemoryPersistenceFacade
        try:
            facade = MemoryPersistenceFacade(self._session_factory)
            profile = await facade.get_profile(user_id)
            return profile.to_dict()
        except Exception:
            return {"correct_rate": 0.5, "total_questions": 0}

    async def _get_user_skills_dict(self, user_id: str) -> Dict[str, Any]:
        try:
            skills = await self._skill_aggregator.get_all_skills(user_id)
            return {s["skill_code"]: s for s in skills}
        except Exception:
            return {}

    async def _get_recently_done_ids(self, user_id: str) -> List[str]:
        try:
            async with self._session_factory() as db:
                thirty_days_ago = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                result = await db.execute(
                    select(LearningRecord.question_id).where(
                        and_(LearningRecord.user_id == user_id, LearningRecord.question_id.isnot(None),
                             LearningRecord.created_at >= thirty_days_ago)
                    ).limit(200)
                )
                return [r[0] for r in result.fetchall() if r[0]]
        except Exception:
            return []

    async def _determine_target(
        self, target_category: str, user_skills: Dict[str, Any], user_profile: Dict[str, Any]
    ) -> Tuple[str, List[str]]:
        if target_category:
            return target_category, []
        weak_points = user_profile.get("weak_points", [])
        if weak_points:
            return weak_points[0].get("category", "导数"), [w.get("category", "") for w in weak_points]
        return "导数", []

    async def _sql_retrieval(
        self, category: str, difficulty: int, exclude_ids: List[str], count: int
    ) -> List[Question]:
        async with self._session_factory() as db:
            query = select(Question).where(
                and_(Question.category == category, Question.difficulty == difficulty, Question.is_active == True)
            )
            if exclude_ids:
                query = query.where(Question.id.notin_(exclude_ids))
            query = query.order_by(Question.usage_count.asc()).limit(count * 2)
            result = await db.execute(query)
            questions = list(result.scalars().all())

            if len(questions) < count:
                relaxed = select(Question).where(
                    and_(Question.category == category,
                         Question.difficulty.between(max(1, difficulty - 1), min(5, difficulty + 1)),
                         Question.is_active == True)
                )
                if exclude_ids:
                    relaxed = relaxed.where(Question.id.notin_(exclude_ids))
                relaxed = relaxed.order_by(Question.usage_count.asc()).limit(count * 3)
                result = await db.execute(relaxed)
                questions = list(result.scalars().all())
            return questions

    async def _vector_retrieval(self, category: str, difficulty: int, count: int) -> List[Dict]:
        try:
            query_text = f"{category} 数学题目 难度{difficulty}"
            results = await self._vector_store.hybrid_search(
                query=query_text, category_filter=category,
                difficulty_range=(max(1, difficulty - 1), min(5, difficulty + 1)),
                n_results=count,
            )
            return [{
                "id": r.id, "content": r.content,
                "category": r.metadata.get("category", category),
                "difficulty": r.metadata.get("difficulty", difficulty),
                "score": r.score, "source": "vector",
            } for r in results]
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    async def _kg_analysis(self, category: str, user_skills: Dict[str, Any]) -> List[Dict]:
        try:
            from app.services.math_skill_dag import MathSkillDAG
            dag = MathSkillDAG()
            target_skills = [code for code, node in dag._graph.items() if node.get("category") == category]
            if not target_skills:
                return []
            mastered = {code for code, s in user_skills.items() if s.get("status") == "mastered"}
            suggestions = []
            for skill_code in target_skills:
                prereqs = dag.get_prerequisites(skill_code)
                missing = [p for p in prereqs if p not in mastered]
                if missing:
                    suggestions.append({"skill_code": skill_code, "missing_prerequisites": missing, "suggestion": "建议先巩固前置知识点"})
            return suggestions
        except Exception as e:
            logger.warning(f"知识图谱分析失败: {e}")
            return []

    async def _fuse_and_rank(
        self, sql_results: List[Question], vector_results: List[Dict],
        kg_suggestions: List[Dict], target_count: int, difficulty: int,
    ) -> List[Question]:
        seen_ids = set()
        final = []
        for q in sql_results:
            if q.id not in seen_ids:
                final.append(q)
                seen_ids.add(q.id)
        if len(final) < target_count and vector_results:
            vector_ids = [v["id"] for v in vector_results if v["id"] not in seen_ids]
            if vector_ids:
                await self._fetch_vector_questions(vector_ids, final, seen_ids)
        final.sort(key=lambda q: q.usage_count if q.usage_count else 0)
        return final[:target_count]

    async def _fetch_vector_questions(self, vector_ids: List[str], final: List[Question], seen_ids: set):
        async with self._session_factory() as db:
            result = await db.execute(select(Question).where(Question.id.in_(vector_ids)))
            for q in result.scalars().all():
                if q.id not in seen_ids:
                    final.append(q)
                    seen_ids.add(q.id)

    async def _generate_ai_analysis(
        self, user_profile: Dict, questions: List[Question],
        difficulty: int, weak_points: List[str], target_category: str,
    ) -> Dict[str, Any]:
        correct_rate = user_profile.get("correct_rate", 0.5)
        question_summaries = [f"- {q.content[:80]}... (难度:{q.difficulty})" for q in questions]
        system_prompt = (
            "你是一位数学教育专家。请根据学生信息，用简洁专业的语言给出推荐理由。\n"
            "严格按JSON格式返回（不要用markdown代码块）：\n"
            '{"assessment": "水平评估", "recommendation_reason": "推荐原因", "learning_advice": "学习建议", "estimated_time_minutes": 数字}'
        )
        prompt = (
            f"### 学生概况\n- 正确率: {correct_rate:.0%}\n- 薄弱点: {weak_points or target_category}\n- 推荐难度: {difficulty}/5\n\n"
            f"### 推荐题目\n共{len(questions)}道{target_category}题目：\n" + "\n".join(question_summaries)
        )
        try:
            # AI分析使用快速模型(qwen-turbo)，不需要最强推理能力
            response = await self._llm.generate(
                prompt=prompt, system_prompt=system_prompt,
                temperature=0.3,
                model=settings.LLM_MATH_MODEL or "qwen-turbo",  # 用快速模型
                max_tokens=512,  # 限制输出长度加速
            )
            content = response.content.strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                import re
                m = re.search(r'\{.*\}', content, re.DOTALL)
                return json.loads(m.group()) if m else self._default_analysis(correct_rate, target_category, len(questions), difficulty)
        except Exception:
            return self._default_analysis(correct_rate, target_category, len(questions), difficulty)

    def _default_analysis(self, correct_rate: float, category: str, count: int, difficulty: int) -> Dict:
        return {
            "assessment": f"当前正确率 {correct_rate:.0%}",
            "recommendation_reason": f"推荐{count}道难度{difficulty}/5的{category}题目",
            "learning_advice": "建议先复习概念，再逐一完成",
            "estimated_time_minutes": count * 3,
        }

    async def _get_fallback_recommendation(self, request: RecommendationRequest) -> RecommendationResult:
        logger.info(f"[降级推荐] user={request.user_id}")
        try:
            async with self._session_factory() as db:
                query = select(Question).where(and_(Question.is_active == True, Question.difficulty == 3))
                if request.exclude_ids:
                    query = query.where(Question.id.notin_(request.exclude_ids))
                query = query.limit(request.count)
                result = await db.execute(query)
                questions = list(result.scalars().all())
        except Exception:
            questions = []
        return RecommendationResult(
            questions=[self._question_to_dict(q) for q in questions],
            ai_analysis={},
            meta={"target_category": request.target_category or "auto", "recommended_difficulty": 3, "retrieval_method": "fallback"},
            request_id=request.request_id or f"rec_{int(time.time()*1000)}",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _question_to_dict(q: Question) -> Dict[str, Any]:
        return {
            "id": q.id, "content": q.content, "question_type": q.question_type,
            "options": q.options, "answer": q.answer, "analysis": q.analysis,
            "category": q.category, "sub_categories": q.sub_categories,
            "knowledge_points": q.knowledge_points, "difficulty": q.difficulty,
            "estimated_time": q.estimated_time, "source": q.source,
        } if q else {}


_rag_recommender_instance: Optional[RAGRecommender] = None


async def get_rag_recommender() -> RAGRecommender:
    global _rag_recommender_instance
    if _rag_recommender_instance is None:
        vector_store = await get_vector_store() if settings.RAG_ENABLE_VECTOR_SEARCH else None
        llm_service = get_llm_service() if settings.RAG_ENABLE_AI_EXPLANATION else None
        _rag_recommender_instance = RAGRecommender(
            vector_store=vector_store, llm_service=llm_service,
            difficulty_estimator=DifficultyEstimator(), skill_aggregator=SkillAggregator(),
        )
    return _rag_recommender_instance