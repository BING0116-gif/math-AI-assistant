from fastapi import APIRouter, HTTPException

from app.data.database import get_db_session
from app.services.knowledge_catalog import get_published_course_tree, get_published_learning_content, get_published_point, list_published_courses


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
