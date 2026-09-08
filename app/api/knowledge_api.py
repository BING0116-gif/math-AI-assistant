from fastapi import APIRouter, HTTPException, Query, Request

from app.data.database import get_db_session
from app.services.knowledge_catalog import get_published_course_tree, get_published_learning_content, get_published_point, list_published_courses
from app.services.learning_projection import read_learning_states, state_evidence


router = APIRouter(prefix="/api/knowledge", tags=["知识目录"])


@router.get("/courses")
async def get_courses():
    async with get_db_session() as session:
        return {"courses": await list_published_courses(session)}


@router.get("/courses/{course_id}/tree")
async def get_course_tree(course_id: str):
    async with get_db_session() as session:
        tree = await get_published_course_tree(session, course_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="未找到已发布课程")
    return tree


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
