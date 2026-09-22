"""Read-only queries for published course catalogs."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource


async def get_published_course_tree(session: AsyncSession, course_id: str, version_name: str | None = None) -> dict | None:
    course = (await session.execute(select(Course).where(Course.id == course_id, Course.status == "active"))).scalar_one_or_none()
    if course is None or not course.default_version_id:
        return None
    version_filter = KnowledgeGraphVersion.version == version_name if version_name else KnowledgeGraphVersion.id == course.default_version_id
    version = (await session.execute(select(KnowledgeGraphVersion).where(version_filter, KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.status == "published"))).scalar_one_or_none()
    if version is None:
        return None

    chapters = list((await session.execute(select(Chapter).where(
        Chapter.version_id == version.id, Chapter.status == "published"
    ).order_by(Chapter.sort_order, Chapter.code))).scalars())
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
    # A point from any explicitly requested published version remains readable;
    # the default-version restriction belongs on course discovery, not on the
    # immutable point URL returned by a versioned tree.
    course = (await session.execute(select(Course).where(
        Course.id == point.course_id, Course.status == "active"
    ))).scalar_one_or_none()
    version = (await session.execute(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.id == point.version_id, KnowledgeGraphVersion.status == "published"))).scalar_one_or_none()
    chapter = await session.get(Chapter, point.chapter_id)
    if course is None or version is None or chapter is None or chapter.status != "published":
        return None
    result = _point_summary(point)
    result.update({"course": _course_summary(course), "version": _version_summary(version), "aliases": point.aliases, "learning_objectives": point.learning_objectives, "common_errors": point.common_errors, "key_concepts": point.key_concepts, "key_formulas": point.key_formulas, "exam_focuses": point.exam_focuses, "prerequisites": point.prerequisites, "related": point.related})
    return result


async def get_published_learning_content(session: AsyncSession, point_id: str) -> dict | None:
    point = await get_published_point(session, point_id)
    if point is None:
        return None
    resources = list((await session.execute(
        select(KnowledgePointResource)
        .where(KnowledgePointResource.knowledge_point_id == point_id, KnowledgePointResource.status == "published")
        .order_by(KnowledgePointResource.resource_type, KnowledgePointResource.sort_order)
    )).scalars())
    point["resources"] = [{
        "id": resource.id,
        "type": resource.resource_type,
        "title": resource.title,
        "body": resource.body,
        "metadata": resource.metadata_,
        "source": {
            "document_id": resource.source_document_id,
            "locator": resource.source_locator,
        },
        "review": {
            "status": resource.status,
            "math_validation_status": resource.math_validation_status,
            "reviewed_at": resource.reviewed_at,
            "published_at": resource.published_at,
        },
    } for resource in resources]
    return point


async def search_published_points(
    session: AsyncSession, course_id: str, query: str, version_name: str | None = None, limit: int = 20,
) -> list[dict]:
    """Search the complete published course, independent of the local graph projection."""
    tree = await get_published_course_tree(session, course_id, version_name)
    if tree is None:
        return []
    normalized = query.strip().casefold()
    if not normalized:
        return []
    results: list[dict] = []

    def visit(chapter: dict, root: dict) -> None:
        for point in chapter["knowledge_points"]:
            haystack = [point["name"], point["code"]]
            # Aliases are intentionally omitted from tree summaries; load them
            # only for the small candidate set after name/code matching below.
            if any(normalized in str(value).casefold() for value in haystack):
                results.append({**point, "chapter": {"id": root["id"], "code": root["code"], "name": root["name"]}})
        for child in chapter["children"]:
            visit(child, root)

    for root in tree["chapters"]:
        visit(root, root)
    if len(results) < limit:
        version_id = tree["version"]["id"]
        candidates = list((await session.scalars(select(KnowledgePoint).join(Chapter).where(
            KnowledgePoint.version_id == version_id,
            KnowledgePoint.status == "active",
            Chapter.status == "published",
        ))).all())
        existing = {row["id"] for row in results}
        chapter_by_id: dict[str, dict] = {}

        def index_chapters(chapter: dict, root: dict) -> None:
            chapter_by_id[chapter["id"]] = root
            for child in chapter["children"]:
                index_chapters(child, root)

        for root in tree["chapters"]:
            index_chapters(root, root)
        for point in candidates:
            if point.id in existing or not any(normalized in str(alias).casefold() for alias in (point.aliases or [])):
                continue
            chapter = chapter_by_id.get(point.chapter_id)
            if chapter:
                results.append({**_point_summary(point), "chapter": {"id": chapter["id"], "code": chapter["code"], "name": chapter["name"]}})
    return results[:limit]


def _course_summary(course: Course) -> dict:
    return {"id": course.id, "code": course.code, "name": course.name, "description": course.description, "subject": course.subject}


def _version_summary(version: KnowledgeGraphVersion) -> dict:
    return {"id": version.id, "version": version.version, "name": version.name, "status": version.status}


def _point_summary(point: KnowledgePoint) -> dict:
    return {"id": point.id, "code": point.code, "name": point.name, "description": point.description, "difficulty": point.difficulty, "importance": point.importance, "sort_order": point.sort_order, "prerequisites": point.prerequisites, "related": point.related}
