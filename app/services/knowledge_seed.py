"""Idempotent seed data for the Phase 1 calculus course catalog."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import Chapter, Course, KnowledgeGraphVersion, KnowledgePoint


COURSE_CODE = "advanced-calculus"
VERSION = "1.0"

SECTIONS = [
    ("function-basics", "函数基础", "函数的表示、定义域与基本性质。", 1),
    ("limit-concept", "极限概念", "理解数列与函数极限的基本语言。", 2),
    ("limit-calculation", "极限计算", "使用等价无穷小、夹逼和四则运算法则计算极限。", 3),
]

POINTS = [
    ("function-definition", "函数的定义", "理解函数、定义域和值域的关系。", "function-basics", 1, 1, ["确定函数的定义域和值域"]),
    ("function-properties", "函数的基本性质", "识别单调性、奇偶性和周期性。", "function-basics", 2, 2, ["判断函数的单调性、奇偶性和周期性"]),
    ("elementary-functions", "基本初等函数", "掌握幂、指数、对数、三角函数的基本性质。", "function-basics", 3, 2, ["比较基本初等函数的性质"]),
    ("sequence-limit", "数列极限", "理解数列收敛及其极限。", "limit-concept", 1, 2, ["判断简单数列的收敛性"]),
    ("function-limit", "函数极限", "理解自变量趋近时函数值的变化趋势。", "limit-concept", 2, 2, ["用直观语言描述函数极限"]),
    ("left-right-limit", "左右极限", "区分左极限、右极限与函数极限存在的条件。", "limit-concept", 3, 3, ["判断分段函数在一点的极限是否存在"]),
    ("infinitesimal", "无穷小", "理解无穷小量及其运算性质。", "limit-calculation", 1, 3, ["识别并合成无穷小量"]),
    ("limit-laws", "极限运算法则", "使用和、差、积、商的极限运算法则。", "limit-calculation", 2, 3, ["运用极限四则运算法则"]),
    ("equivalent-infinitesimal", "等价无穷小替换", "在适用条件下用等价无穷小简化极限。", "limit-calculation", 3, 4, ["完成常见等价无穷小替换"]),
    ("squeeze-theorem", "夹逼定理", "通过上下界相同的极限确定目标极限。", "limit-calculation", 4, 3, ["运用夹逼定理求极限"]),
]


async def seed_phase_one_calculus(session: AsyncSession) -> Course:
    """Create or refresh the fixed Phase 1 demo catalog without duplicate records."""
    course = (await session.execute(select(Course).where(Course.code == COURSE_CODE))).scalar_one_or_none()
    if course is None:
        course = Course(code=COURSE_CODE, name="高等数学", description="Phase 1 演示课程：函数与极限。", subject="数学")
        session.add(course)
        await session.flush()

    graph_version = (await session.execute(
        select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == VERSION)
    )).scalar_one_or_none()
    if graph_version is None:
        graph_version = KnowledgeGraphVersion(
            course_id=course.id, version=VERSION, name="函数与极限（演示版）", status="published", published_at=datetime.now(timezone.utc)
        )
        session.add(graph_version)
        await session.flush()
    elif graph_version.status != "published":
        graph_version.status = "published"

    course.default_version_id = graph_version.id
    sections_by_code = {}
    for code, name, description, sort_order in SECTIONS:
        section = (await session.execute(select(Chapter).where(Chapter.version_id == graph_version.id, Chapter.code == code))).scalar_one_or_none()
        if section is None:
            section = Chapter(course_id=course.id, version_id=graph_version.id, code=code, name=name, description=description, sort_order=sort_order, level=2)
            session.add(section)
            await session.flush()
        sections_by_code[code] = section

    chapter = (await session.execute(select(Chapter).where(Chapter.version_id == graph_version.id, Chapter.code == "functions-and-limits"))).scalar_one_or_none()
    if chapter is None:
        chapter = Chapter(course_id=course.id, version_id=graph_version.id, code="functions-and-limits", name="函数与极限", description="高等数学的第一章。", sort_order=1, level=1)
        session.add(chapter)
        await session.flush()
    for section in sections_by_code.values():
        section.parent_id = chapter.id

    for code, name, description, section_code, sort_order, difficulty, objectives in POINTS:
        point = (await session.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == graph_version.id, KnowledgePoint.code == code))).scalar_one_or_none()
        if point is None:
            point = KnowledgePoint(course_id=course.id, version_id=graph_version.id, chapter_id=sections_by_code[section_code].id, code=code, name=name, description=description, aliases=[], learning_objectives=objectives, common_errors=[], difficulty=difficulty, importance=0.8, sort_order=sort_order, status="active")
            session.add(point)
    await session.flush()
    return course
