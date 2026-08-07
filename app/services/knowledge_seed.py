"""Idempotent seed data for the Phase 1 calculus course catalog."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource


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

POINT_DETAILS = {
    "function-definition": {"concepts": ["定义域", "对应关系", "值域"], "formulas": ["y = f(x)"], "exam_focuses": ["求定义域", "判断是否构成函数"]},
    "function-properties": {"concepts": ["单调性", "奇偶性", "周期性"], "formulas": ["f(-x) = f(x)", "f(-x) = -f(x)"], "exam_focuses": ["奇偶性判断", "单调区间求解"]},
    "elementary-functions": {"concepts": ["幂函数", "指数函数", "对数函数", "三角函数"], "formulas": ["a^x", "log_a x"], "exam_focuses": ["函数性质比较", "复合函数定义域"]},
    "sequence-limit": {"concepts": ["数列收敛", "极限唯一性"], "formulas": ["lim n→∞ a_n = A"], "exam_focuses": ["数列极限计算", "收敛性判断"]},
    "function-limit": {"concepts": ["自变量趋近", "函数值趋势", "极限存在"], "formulas": ["lim x→x₀ f(x) = A"], "exam_focuses": ["函数极限定义", "极限存在性"]},
    "left-right-limit": {"concepts": ["左极限", "右极限", "分段函数"], "formulas": ["lim x→x₀ f(x) 存在 ⇔ 左右极限相等"], "exam_focuses": ["分段函数极限", "间断点判断"]},
    "infinitesimal": {"concepts": ["无穷小", "高阶无穷小", "同阶无穷小"], "formulas": ["lim x→x₀ α(x) = 0"], "exam_focuses": ["无穷小比较", "无穷小运算"]},
    "limit-laws": {"concepts": ["四则运算法则", "连续代入"], "formulas": ["lim(f±g)=lim f±lim g", "lim(fg)=lim f·lim g"], "exam_focuses": ["直接代入", "有理化与通分"]},
    "equivalent-infinitesimal": {"concepts": ["等价无穷小", "替换条件"], "formulas": ["sin x ~ x", "1-cos x ~ x²/2", "ln(1+x) ~ x"], "exam_focuses": ["等价替换求极限", "替换适用范围"]},
    "squeeze-theorem": {"concepts": ["夹逼定理", "上下界"], "formulas": ["g(x) ≤ f(x) ≤ h(x)"], "exam_focuses": ["三角函数夹逼", "振荡函数极限"]},
}


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
        detail = POINT_DETAILS[code]
        if point is None:
            point = KnowledgePoint(course_id=course.id, version_id=graph_version.id, chapter_id=sections_by_code[section_code].id, code=code, name=name, description=description, aliases=[], learning_objectives=objectives, common_errors=[], difficulty=difficulty, importance=0.8, sort_order=sort_order, status="active")
            session.add(point)
        point.key_concepts = detail["concepts"]
        point.key_formulas = detail["formulas"]
        point.exam_focuses = detail["exam_focuses"]
    await session.flush()
    points = list((await session.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == graph_version.id))).scalars())
    for point in points:
        detail = POINT_DETAILS[point.code]
        resources = [
            ("concept", "核心概念", "、".join(detail["concepts"]), 1),
            ("formula", "常用公式", "\n".join(detail["formulas"]), 2),
            ("exam_focus", "常见考点", "、".join(detail["exam_focuses"]), 3),
            ("example", "例题：理解与应用", f"围绕「{point.name}」的典型例题将在这里呈现，包含题干、分步解析与易错提醒。", 4),
            ("exercise", "巩固练习", f"完成「{point.name}」的分层练习后，系统会据此更新学习建议。", 5),
        ]
        for resource_type, title, body, sort_order in resources:
            resource = (await session.execute(select(KnowledgePointResource).where(KnowledgePointResource.knowledge_point_id == point.id, KnowledgePointResource.resource_type == resource_type, KnowledgePointResource.title == title))).scalar_one_or_none()
            if resource is None:
                session.add(KnowledgePointResource(knowledge_point_id=point.id, resource_type=resource_type, title=title, body=body, sort_order=sort_order, status="published"))
            else:
                resource.body = body
    return course
