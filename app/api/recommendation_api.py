"""
推荐系统 API 接口 — 提供 RESTful API 端点。

端点列表：
- POST /api/recommend/questions    获取个性化推荐题目
- POST /api/recommend/explain      获取推荐解释
- GET  /api/recommend/skill-profile 获取技能画像摘要
- POST /api/recommend/ai-analyze   AI分析题目难度
- POST /api/recommend/questions/import 批量导入题目(JSON)
- POST /api/recommend/pdf-import    PDF文件导入题库
- POST /api/recommend/vector-search    向量搜索
- GET  /api/recommend/health       健康检查
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.services.rag_recommender import (
    RecommendationRequest, get_rag_recommender,
)
from app.services.vector_store import get_vector_store
from app.services.llm_service import get_llm_service
from app.config.settings import settings
from app.middleware.auth import verify_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["智能推荐"])


def _get_user_id(http_request: Request) -> Optional[str]:
    """Extract user_id from request state or verify token directly."""
    # Try from middleware state first
    user_id = getattr(http_request.state, "user_id", None)
    if user_id:
        return user_id
    # Fallback: verify token directly
    auth_header = http_request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return verify_access_token(token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    return None


class RecommendQuestionsRequest(BaseModel):
    target_category: Optional[str] = Field(None)
    count: int = Field(default=5, ge=1, le=20)
    context: str = Field(default="practice")
    exclude_ids: List[str] = Field(default_factory=list)


class ImportQuestionsRequest(BaseModel):
    questions: List[Dict[str, Any]]


class VectorSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    difficulty_min: Optional[int] = Field(None, ge=1, le=5)
    difficulty_max: Optional[int] = Field(None, ge=1, le=5)
    n_results: int = Field(default=10, ge=1, le=50)


@router.post("/questions")
async def recommend_questions(request: RecommendQuestionsRequest, http_request: Request, background_tasks: BackgroundTasks):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        recommender = await get_rag_recommender()
        result = await recommender.recommend(RecommendationRequest(
            user_id=user_id, target_category=request.target_category or "",
            count=request.count, context=request.context,
            exclude_ids=request.exclude_ids or [],
        ))
        return {
            "success": True,
            "data": {"questions": result.questions, "ai_analysis": result.ai_analysis, "meta": result.meta},
            "request_id": result.request_id,
            "generated_at": result.generated_at,
            "processing_time_ms": result.processing_time_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推荐失败: {str(e)}")


@router.post("/explain")
async def explain_recommendation(request: RecommendQuestionsRequest, http_request: Request):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        recommender = await get_rag_recommender()
        result = await recommender.recommend(RecommendationRequest(
            user_id=user_id, target_category=request.target_category or "",
            count=min(request.count, 3), context=request.context,
            exclude_ids=request.exclude_ids or [],
        ))
        return {"success": True, "data": {"ai_analysis": result.ai_analysis, "meta": result.meta}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skill-profile")
async def get_skill_profile(http_request: Request):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile(user_id)
        return {
            "success": True,
            "data": {
                "user_id": user_id, "correct_rate": profile.correct_rate,
                "recommended_difficulty": profile.recommended_difficulty,
                "weak_points": profile.weak_points[:5], "strong_points": profile.strong_points[:5],
                "total_skills": len(profile.skills),
                "mastered_count": sum(1 for s in profile.skills if s["status"] == "mastered"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-analyze")
async def ai_analyze_question(http_request: Request):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")

        body = await http_request.json()
        question_content = body.get("content", "")
        category = body.get("category", "数学")
        if not question_content:
            raise HTTPException(status_code=400, detail="题目内容不能为空")
        result = await get_llm_service().analyze_question_difficulty(question_content, category)
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/questions/import")
async def import_questions(request: ImportQuestionsRequest, http_request: Request):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        from app.services.question_importer import QuestionImporter
        vs = await get_vector_store()
        importer = QuestionImporter(vector_store=vs)
        result = await importer.import_from_dict_list(request.questions)
        return {"success": True, "data": {"total": result.total, "success": result.success, "failed": result.failed, "imported_ids": result.imported_ids}, "errors": result.errors[:10] if result.errors else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector-search")
async def vector_search(request: VectorSearchRequest, http_request: Request):
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        vs = await get_vector_store()
        difficulty_range = None
        if request.difficulty_min and request.difficulty_max:
            difficulty_range = (request.difficulty_min, request.difficulty_max)
        results = await vs.hybrid_search(query=request.query, category_filter=request.category, difficulty_range=difficulty_range, n_results=request.n_results)
        return {"success": True, "data": {"results": [{"id": r.id, "content": r.content[:100], "category": r.metadata.get("category", ""), "difficulty": r.metadata.get("difficulty", ""), "score": round(r.score, 3)} for r in results], "total": len(results)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdf-import")
async def import_pdf_questions(
    http_request: Request,
    question_file: UploadFile = File(..., description="题目PDF文件"),
    answer_file: Optional[UploadFile] = File(None, description="答案PDF文件（可选）"),
    category: str = Form(default="", description="题目分类"),
    source: str = Form(default="", description="来源名称"),
    difficulty: int = Form(default=3, ge=1, le=5, description="默认难度1-5"),
):
    """
    上传PDF文件导入题库。
    
    支持格式：
      - 题目PDF（必需）：包含题目内容，支持选择题/填空题/解答题/计算题/证明题等混合题型
      - 答案PDF（可选）：对应答案文件
    
    返回解析预览和导入结果。
    """
    try:
        user_id = _get_user_id(http_request)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")

        # 验证文件类型
        if not question_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="题目文件必须是PDF格式")
        if answer_file and not answer_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="答案文件必须是PDF格式")

        # 保存上传的临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as q_tmp:
            q_tmp.write(await question_file.read())
            q_path = q_tmp.name

        a_path = None
        if answer_file and await answer_file.read():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as a_tmp:
                a_tmp.write(await answer_file.read())
                a_path = a_tmp.name

        try:
            # 解析PDF
            from app.services.pdf_question_parser import PDFQuestionParser
            parser = PDFQuestionParser(
                default_difficulty=difficulty,
                default_category=category or "未分类",
            )
            parse_result = await parser.parse(
                question_pdf_path=q_path,
                answer_pdf_path=a_path,
            )

            if not parse_result.success:
                return {
                    "success": False,
                    "data": None,
                    "errors": parse_result.errors,
                }

            # 转换并导入
            from app.services.question_importer import QuestionImporter
            vs = await get_vector_store()
            importer = QuestionImporter(vector_store=vs)
            import_dicts = parser.to_import_dicts(parse_result, category=category, source_name=source)
            result = await importer.import_from_dict_list(import_dicts)

            return {
                "success": True,
                "data": {
                    "parsed_count": parse_result.total_questions,
                    "imported_total": result.total,
                    "imported_success": result.success,
                    "imported_failed": result.failed,
                    "imported_ids": result.imported_ids,
                    "preview": [
                        {
                            "number": q.number,
                            "type": q.question_type,
                            "content_preview": q.content[:80],
                            "has_answer": bool(q.answer),
                        }
                        for q in parse_result.questions[:10]
                    ],
                },
                "warnings": parse_result.warnings,
                "errors": result.errors[:10] if result.errors else None,
            }
        finally:
            # 清理临时文件
            os.unlink(q_path)
            if a_path and os.path.exists(a_path):
                os.unlink(a_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF导入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF导入失败: {str(e)}")


@router.get("/health")
async def recommend_health():
    checks = {}
    try:
        llm = get_llm_service()
        checks["llm_service"] = {"status": "ready", "cache": llm.get_cache_stats()}
    except Exception as e:
        checks["llm_service"] = {"status": "error", "detail": str(e)}
    try:
        vs = await get_vector_store()
        stats = await vs.get_collection_stats()
        checks["vector_store"] = {"status": "ready", "stats": stats}
    except Exception as e:
        checks["vector_store"] = {"status": "error", "detail": str(e)}
    return {"status": "healthy" if all(c.get("status") == "ready" for c in checks.values()) else "degraded", "service": "rag-recommendation-engine", "checks": checks}