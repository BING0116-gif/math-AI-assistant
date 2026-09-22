from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.data.database import get_db_session
from app.services.knowledge_catalog import get_published_course_tree, get_published_learning_content, get_published_point, list_published_courses, search_published_points
from app.services.learning_projection import read_learning_states, state_evidence
from app.services.knowledge_learning_map import build_learning_map


router = APIRouter(prefix="/api/knowledge", tags=["知识目录"])


class LearningMapPoint(BaseModel):
    id: str
    code: str
    status: Literal["unlearned", "learning", "weak", "mastered", "locked"]
    mastery: float
    attempts: int
    correct: int
    evidence: dict
    missing_prerequisites: list[str]
    review_due: bool
    review_due_at: datetime | None
    review_schedule_id: int | None
    open_error_count: int
    due_error_count: int


class LearningMapRecommendation(BaseModel):
    knowledge_point_id: str
    knowledge_point_code: str
    rank: int
    kind: Literal["primary", "secondary"]
    reason_code: str
    reason: str


class LearningMapResponse(BaseModel):
    course_id: str
    version_id: str
    generated_at: datetime
    points: list[LearningMapPoint]
    primary_recommendation: LearningMapRecommendation | None
    secondary_recommendations: list[LearningMapRecommendation]


@router.get("/courses")
async def get_courses():
    async with get_db_session() as session:
        return {"courses": await list_published_courses(session)}


@router.get("/courses/{course_id}/tree")
async def get_course_tree(course_id: str, version: str | None = Query(default=None, max_length=40)):
    async with get_db_session() as session:
        tree = await get_published_course_tree(session, course_id, version)
    if tree is None:
        raise HTTPException(status_code=404, detail="未找到已发布课程")
    return tree


@router.get("/courses/{course_id}/search")
async def search_course_points(
    course_id: str,
    q: str = Query(..., min_length=1, max_length=100),
    version: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=50),
):
    async with get_db_session() as session:
        tree = await get_published_course_tree(session, course_id, version)
        if tree is None:
            raise HTTPException(status_code=404, detail="未找到已发布课程")
        results = await search_published_points(session, course_id, q, version, limit)
    return {"course_id": course_id, "version": tree["version"], "query": q, "results": results}


@router.get("/courses/{course_id}/learning-map", response_model=LearningMapResponse)
async def get_course_learning_map(course_id: str, request: Request):
    """Return the current authenticated user's projection; user_id is never client supplied."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    async with get_db_session() as session:
        projection = await build_learning_map(session, course_id, str(user_id))
    if projection is None:
        raise HTTPException(status_code=404, detail="未找到已发布课程")
    return projection


@router.get("/points/{point_id}")
async def get_point(point_id: str):
    async with get_db_session() as session:
        point = await get_published_point(session, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="未找到已发布知识点")
    return point


@router.get("/points/{point_id}/learning")
async def get_learning_content(point_id: str):
    async with get_db_session() as session:
        content = await get_published_learning_content(session, point_id)
    if content is None:
        raise HTTPException(status_code=404, detail="未找到已发布知识点")
    return content


def _map_mastery_status(mastery: float, attempts: int) -> str:
    """将掌握度数值映射为前端着色的四态。

    - untouched: 从未练习 / 无掌握度记录
    - weak:      有练习但掌握度低于 0.30（薄弱）
    - learning:  掌握度 0.30 ~ 0.85（学习中）
    - mastered:  掌握度 >= 0.85（已掌握）
    阈值与 skill_aggregator.SKILL_THRESHOLDS 保持一致。
    """
    if attempts <= 0 or mastery <= 0:
        return "untouched"
    if mastery >= 0.85:
        return "mastered"
    if mastery >= 0.30:
        return "learning"
    return "weak"


@router.get("/mastery")
async def get_mastery(request: Request, course_id: str = Query(...)):
    """按课程返回当前用户的掌握度（以 knowledge_point_code 为 key）。

    未登录时返回空映射，前端可正常渲染（全部视为未学）。
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return {"mastery": {}}

    from sqlalchemy import select

    from app.data.models import KnowledgePoint, UserKnowledgeState

    async with get_db_session() as session:
        codes = list((await session.execute(
            select(KnowledgePoint.code).where(
                KnowledgePoint.course_id == course_id,
                KnowledgePoint.status == "active",
            )
        )).scalars())
        states = [state for state in await read_learning_states(session, user_id)
                  if state.knowledge_point_code in codes]

    mastery = {
        state.knowledge_point_code: {
            **state_evidence(state),
            "mastery": state.mastery,
            "attempts": state.attempts_count,
            "correct": state.correct_count,
            "status": _map_mastery_status(state.mastery, state.attempts_count),
        }
        for state in states
    }
    return {"mastery": mastery}
