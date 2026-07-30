"""Read-only queries for published course catalogs."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import Chapter, Course, KnowledgeGraphVersion, KnowledgePoint


async def get_published_course_tree(session: AsyncSession, course_id: str) -> dict | None:
    course = (await session.execute(select(Course).where(Course.id == course_id, Course.status == "active"))).scalar_one_or_none()
    if course is None or not course.default_version_id:
        return None
    version = (await session.execute(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.id == course.default_version_id, KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.status == "published"))).scalar_one_or_none()
    if version is None:
        return None

    chapters = list((await session.execute(select(Chapter).where(Chapter.version_id == version.id).order_by(Chapter.sort_order, Chapter.code))).scalars())
    points = list((await session.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == version.id, KnowledgePoint.status == "active").order_by(KnowledgePoint.sort_order, KnowledgePoint.code))).scalars())
    children: dict[str | None, list[dict]] = {}
    for chapter in chapters:
        children.setdefault(chapter.parent_id, []).append({"id": chapter.id, "code": chapter.code, "name": chapter.name, "description": chapter.description, "sort_order": chapter.sort_order, "level": chapter.level, "children": [], "knowledge_points": []})
    by_id = {item["id"]: item for items in children.values() for item in items}
    for point in points:
        if point.chapter_id in by_id:
            by_id[point.chapter_id]["knowledge_points"].append(_point_summary(point))
    for parent_id, nodes in children.items():
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"] = nodes
    return {"course": _course_summary(course), "version": _version_summary(version), "chapters": children.get(None, [])}


async def list_published_courses(session: AsyncSession) -> list[dict]:
    courses = list((await session.execute(
        select(Course)
        .join(KnowledgeGraphVersion, Course.default_version_id == KnowledgeGraphVersion.id)
        .where(Course.status == "active", KnowledgeGraphVersion.status == "published")
        .order_by(Course.name)
    )).scalars())
    return [_course_summary(course) for course in courses]


async def get_published_point(session: AsyncSession, point_id: str) -> dict | None:
    point = (await session.execute(select(KnowledgePoint).where(KnowledgePoint.id == point_id, KnowledgePoint.status == "active"))).scalar_one_or_none()
    if point is None:
        return None
    course = (await session.execute(select(Course).where(Course.id == point.course_id, Course.default_version_id == point.version_id, Course.status == "active"))).scalar_one_or_none()
    version = (await session.execute(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.id == point.version_id, KnowledgeGraphVersion.status == "published"))).scalar_one_or_none()
    if course is None or version is None:
        return None
    result = _point_summary(point)
    result.update({"course": _course_summary(course), "version": _version_summary(version), "aliases": point.aliases, "learning_objectives": point.learning_objectives, "common_errors": point.common_errors})
    return result


def _course_summary(course: Course) -> dict:
    return {"id": course.id, "code": course.code, "name": course.name, "description": course.description, "subject": course.subject}


def _version_summary(version: KnowledgeGraphVersion) -> dict:
    return {"id": version.id, "version": version.version, "name": version.name, "status": version.status}


def _point_summary(point: KnowledgePoint) -> dict:
    return {"id": point.id, "code": point.code, "name": point.name, "description": point.description, "difficulty": point.difficulty, "importance": point.importance, "sort_order": point.sort_order}
