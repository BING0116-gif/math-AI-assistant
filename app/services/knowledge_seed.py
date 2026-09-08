"""Idempotent seed data for the Phase 1 calculus course catalog.

Step 1.1 froze the knowledge system for 函数 / 极限 / 连续 into 24 stable
knowledge points across 4 sections, each with prerequisites / related codes.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models import Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, KnowledgePointResource

logger = logging.getLogger(__name__)


COURSE_CODE = "advanced-calculus"
VERSION = "1.0"

# (code, name, description, sort_order)
SECTIONS = [
    ("function-basics", "函数基础", "函数的表示、定义域、基本性质与基本初等函数。", 1),
    ("limit-concept", "极限概念", "理解数列与函数极限的基本语言与性质。", 2),
    ("limit-calculation", "极限计算", "使用四则运算、重要极限、等价无穷小替换与夹逼定理计算极限。", 3),
    ("continuity", "连续性", "函数的连续、间断点分类与闭区间上连续函数的性质。", 4),
]

# (code, name, description, section_code, sort_order, difficulty, objectives, prerequisites, related)
POINTS = [
    # ── 函数基础 ──
    ("function-definition", "函数的定义", "理解函数、定义域、值域与对应关系。", "function-basics", 1, 1,
     ["确定函数的定义域和值域", "判断变量间是否构成函数"],
     [], ["function-properties", "elementary-functions"]),
    ("function-domain-range", "定义域与值域", "求函数定义域与值域，处理常见限制条件。", "function-basics", 2, 1,
     ["求复合函数与含根号/分母/对数的定义域", "求简单函数的值域"],
     ["function-definition"], ["piecewise-function", "composite-function"]),
    ("function-properties", "函数的基本性质", "识别有界性、单调性、奇偶性与周期性。", "function-basics", 3, 2,
     ["判断函数的有界、单调、奇偶、周期性"],
     ["function-definition"], ["elementary-functions", "function-arithmetic"]),
    ("elementary-functions", "基本初等函数", "掌握幂、指数、对数、三角与反三角函数的性质。", "function-basics", 4, 2,
     ["比较基本初等函数的定义域与值域", "判断基本初等函数的单调区间"],
     ["function-definition"], ["composite-function", "inverse-function"]),
    ("composite-function", "复合函数", "求复合函数的表达式与定义域。", "function-basics", 5, 2,
     ["写出复合函数", "求复合函数的定义域"],
     ["function-definition", "elementary-functions"], ["inverse-function", "function-domain-range"]),
    ("inverse-function", "反函数", "求简单函数的反函数并判断其存在性。", "function-basics", 6, 2,
     ["求单调函数的反函数", "判断反函数是否存在"],
     ["function-definition", "elementary-functions"], ["composite-function", "function-properties"]),
    ("piecewise-function", "分段函数", "理解分段函数的定义与分段点处的行为。", "function-basics", 7, 2,
     ["求分段函数的函数值", "讨论分段点处的极限与连续性"],
     ["function-definition", "function-domain-range"], ["left-right-limit", "discontinuity-classification"]),
    ("function-arithmetic", "函数的四则运算", "两个函数和差积商的运算与定义域。", "function-basics", 8, 1,
     ["求函数的四则运算结果", "确定运算后函数的定义域"],
     ["function-definition"], ["function-properties", "composite-function"]),
    # ── 极限概念 ──
    ("sequence-limit", "数列极限", "理解数列收敛及其极限的直观与定义。", "limit-concept", 1, 2,
     ["判断简单数列的收敛性", "用极限语言描述收敛"],
     ["function-definition"], ["function-limit", "monotone-convergence"]),
    ("function-limit", "函数极限", "理解自变量趋近时函数值的变化趋势。", "limit-concept", 2, 2,
     ["用直观语言描述函数极限", "判断简单函数极限是否存在"],
     ["sequence-limit"], ["left-right-limit", "limit-properties"]),
    ("left-right-limit", "左右极限", "区分左极限、右极限与函数极限存在的条件。", "limit-concept", 3, 3,
     ["判断分段函数在一点的极限是否存在"],
     ["function-limit"], ["piecewise-function", "discontinuity-classification"]),
    ("limit-properties", "极限的性质", "极限的唯一性、局部有界性与局部保号性。", "limit-concept", 4, 3,
     ["应用极限的唯一性与局部保号性解题"],
     ["function-limit"], ["important-limits", "limit-arithmetic-laws"]),
    ("infinitesimal", "无穷小与无穷大", "理解无穷小量、无穷大量及其比较。", "limit-concept", 5, 3,
     ["识别并比较无穷小量", "处理无穷大量"],
     ["function-limit"], ["equivalent-infinitesimal"]),
    ("monotone-convergence", "单调有界准则", "利用单调有界准则判断数列收敛。", "limit-concept", 6, 3,
     ["证明单调有界数列收敛", "由递推证明极限存在"],
     ["sequence-limit"], ["squeeze-theorem"]),
    # ── 极限计算 ──
    ("limit-arithmetic-laws", "极限四则运算法则", "使用和差积商的极限运算法则。", "limit-calculation", 1, 3,
     ["运用极限四则运算法则", "处理直接代入与未定型"],
     ["function-limit", "limit-properties"], ["important-limits", "equivalent-infinitesimal"]),
    ("important-limits", "两个重要极限", "掌握 $\\lim\\frac{\\sin x}{x}=1$ 与 $(1+\\frac{1}{x})^x\\to e$。", "limit-calculation", 2, 3,
     ["应用两个重要极限求极限"],
     ["limit-arithmetic-laws"], ["equivalent-infinitesimal", "squeeze-theorem"]),
    ("equivalent-infinitesimal", "等价无穷小替换", "在适用条件下用等价无穷小简化极限。", "limit-calculation", 3, 4,
     ["完成常见等价无穷小替换", "判断替换的适用范围"],
     ["infinitesimal", "limit-arithmetic-laws"], ["important-limits"]),
    ("squeeze-theorem", "夹逼定理", "通过上下界相同的极限确定目标极限。", "limit-calculation", 4, 3,
     ["运用夹逼定理求极限"],
     ["function-limit"], ["monotone-convergence", "important-limits"]),
    # ── 连续性 ──
    ("continuity-definition", "连续的定义", "函数在一点连续与区间连续的定义。", "continuity", 1, 2,
     ["判断函数在一点的连续性", "用定义证明连续性"],
     ["function-limit", "left-right-limit"], ["discontinuity-classification", "continuity-properties"]),
    ("discontinuity-classification", "间断点及其分类", "区分可去、跳跃与无穷间断点。", "continuity", 2, 3,
     ["判定间断点类型", "讨论分段函数在分段点的连续性"],
     ["continuity-definition", "left-right-limit"], ["piecewise-function"]),
    ("continuity-properties", "连续函数的局部性质", "连续函数运算、复合与反函数保持连续性。", "continuity", 3, 2,
     ["利用连续函数的运算性质", "判断复合函数的连续性"],
     ["continuity-definition"], ["composite-continuity", "closed-interval-properties"]),
    ("composite-continuity", "复合函数与初等函数的连续性", "基本初等函数及其复合在其定义域内连续。", "continuity", 4, 2,
     ["利用初等函数连续性求极限", "判断复合初等函数的连续性"],
     ["continuity-definition", "composite-function"], ["continuity-properties"]),
    ("intermediate-value-theorem", "介值定理", "连续函数在区间上取中间值，用于证根存在。", "continuity", 5, 3,
     ["用介值定理证明方程有实根"],
     ["continuity-properties"], ["closed-interval-properties"]),
    ("closed-interval-properties", "闭区间上连续函数的性质", "闭区间连续函数的有界性与最值定理。", "continuity", 6, 3,
     ["证明闭区间连续函数有界", "应用最值定理"],
     ["continuity-properties"], ["intermediate-value-theorem"]),
]

POINT_DETAILS = {
    "function-definition": {"concepts": ["定义域", "对应关系", "值域"], "formulas": ["y = f(x)"], "exam_focuses": ["求定义域", "判断是否构成函数"]},
    "function-domain-range": {"concepts": ["定义域", "值域", "限制条件"], "formulas": ["x ≥ 0", "x ≠ 0"], "exam_focuses": ["求定义域", "求值域"]},
    "function-properties": {"concepts": ["单调性", "奇偶性", "周期性", "有界性"], "formulas": ["f(-x) = f(x)", "f(-x) = -f(x)"], "exam_focuses": ["奇偶性判断", "单调区间求解"]},
    "elementary-functions": {"concepts": ["幂函数", "指数函数", "对数函数", "三角函数"], "formulas": ["a^x", "log_a x"], "exam_focuses": ["函数性质比较", "复合函数定义域"]},
    "composite-function": {"concepts": ["复合", "中间变量", "定义域"], "formulas": ["f(g(x))"], "exam_focuses": ["求复合函数", "复合定义域"]},
    "inverse-function": {"concepts": ["反函数", "单调性", "存在性"], "formulas": ["y=f^{-1}(x)"], "exam_focuses": ["求反函数", "判断反函数存在"]},
    "piecewise-function": {"concepts": ["分段点", "分段定义", "左右行为"], "formulas": ["f(x)=..."], "exam_focuses": ["求函数值", "分段点极限"]},
    "function-arithmetic": {"concepts": ["和差积商", "定义域"], "formulas": ["(f+g)(x)=f(x)+g(x)"], "exam_focuses": ["四则运算", "定义域"]},
    "sequence-limit": {"concepts": ["数列收敛", "极限唯一性"], "formulas": ["lim n→∞ a_n = A"], "exam_focuses": ["数列极限计算", "收敛性判断"]},
    "function-limit": {"concepts": ["自变量趋近", "函数值趋势", "极限存在"], "formulas": ["lim x→x₀ f(x) = A"], "exam_focuses": ["函数极限定义", "极限存在性"]},
    "left-right-limit": {"concepts": ["左极限", "右极限", "分段函数"], "formulas": ["lim x→x₀ f(x) 存在 ⇔ 左右极限相等"], "exam_focuses": ["分段函数极限", "间断点判断"]},
    "limit-properties": {"concepts": ["唯一性", "局部有界", "局部保号"], "formulas": ["极限唯一"], "exam_focuses": ["唯一性应用", "保号性"]},
    "infinitesimal": {"concepts": ["无穷小", "无穷大", "阶的比较"], "formulas": ["lim x→x₀ α(x) = 0"], "exam_focuses": ["无穷小比较", "无穷大"]},
    "monotone-convergence": {"concepts": ["单调有界", "收敛"], "formulas": ["单调有界 ⇒ 收敛"], "exam_focuses": ["证明收敛", "递推数列"]},
    "limit-arithmetic-laws": {"concepts": ["四则运算法则", "连续代入"], "formulas": ["lim(f±g)=lim f±lim g"], "exam_focuses": ["直接代入", "有理化与通分"]},
    "important-limits": {"concepts": ["重要极限", "e"], "formulas": ["sin x/x → 1", "(1+1/x)^x → e"], "exam_focuses": ["重要极限应用"]},
    "equivalent-infinitesimal": {"concepts": ["等价无穷小", "替换条件"], "formulas": ["sin x ~ x", "1-cos x ~ x²/2", "ln(1+x) ~ x"], "exam_focuses": ["等价替换求极限", "替换适用范围"]},
    "squeeze-theorem": {"concepts": ["夹逼定理", "上下界"], "formulas": ["g(x) ≤ f(x) ≤ h(x)"], "exam_focuses": ["三角函数夹逼", "振荡函数极限"]},
    "continuity-definition": {"concepts": ["连续", "增量", "定义"], "formulas": ["limΔx→0 Δy=0"], "exam_focuses": ["连续性判断", "定义证明"]},
    "discontinuity-classification": {"concepts": ["可去间断", "跳跃间断", "无穷间断"], "formulas": ["左右极限与函数值"], "exam_focuses": ["间断点分类", "分段点"]},
    "continuity-properties": {"concepts": ["运算", "复合", "反函数"], "formulas": ["连续函数四则运算连续"], "exam_focuses": ["运算连续性", "复合连续性"]},
    "composite-continuity": {"concepts": ["初等函数", "复合", "定义域连续"], "formulas": ["初等函数在其定义域内连续"], "exam_focuses": ["利用连续性求极限"]},
    "intermediate-value-theorem": {"concepts": ["介值定理", "零点"], "formulas": ["f(a)f(b)<0 ⇒ 存在零点"], "exam_focuses": ["证根存在"]},
    "closed-interval-properties": {"concepts": ["有界性", "最值定理"], "formulas": ["闭区间连续 ⇒ 有界且有最值"], "exam_focuses": ["最值定理"]},
}


async def seed_phase_one_calculus(session: AsyncSession) -> Course:
    """Create or refresh the fixed Phase 1 catalog without duplicate records."""
    course = (await session.execute(select(Course).where(Course.code == COURSE_CODE))).scalar_one_or_none()
    if course is None:
        course = Course(code=COURSE_CODE, name="高等数学", description="Phase 1 课程：函数、极限与连续。", subject="数学")
        session.add(course)
        await session.flush()

    graph_version = (await session.execute(
        select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.version == VERSION)
    )).scalar_one_or_none()
    if graph_version is None:
        graph_version = KnowledgeGraphVersion(
            course_id=course.id, version=VERSION, name="函数、极限与连续（正式版）", status="published", published_at=datetime.now(timezone.utc)
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
        chapter = Chapter(course_id=course.id, version_id=graph_version.id, code="functions-and-limits", name="函数、极限与连续", description="高等数学的第一章。", sort_order=1, level=1)
        session.add(chapter)
        await session.flush()
    for section in sections_by_code.values():
        section.parent_id = chapter.id

    for code, name, description, section_code, sort_order, difficulty, objectives, prerequisites, related in POINTS:
        point = (await session.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == graph_version.id, KnowledgePoint.code == code))).scalar_one_or_none()
        detail = POINT_DETAILS[code]
        if point is None:
            point = KnowledgePoint(course_id=course.id, version_id=graph_version.id, chapter_id=sections_by_code[section_code].id, code=code, name=name, description=description, aliases=[], learning_objectives=objectives, common_errors=[], difficulty=difficulty, importance=0.8, sort_order=sort_order, status="active")
            session.add(point)
        point.key_concepts = detail["concepts"]
        point.key_formulas = detail["formulas"]
        point.exam_focuses = detail["exam_focuses"]
        point.prerequisites = prerequisites
        point.related = related
    await session.flush()
    points = list((await session.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == graph_version.id))).scalars())
    for point in points:
        detail = POINT_DETAILS.get(point.code)
        if detail is None:
            # 版本库中残留了正式 taxonomy 之外的旧 code（如历史演示版 'limit-laws'）。
            # 不为这类陈旧行添加 alias；跳过即可让 seed 幂等，残留行由 dev DB 重置清理。
            logger.warning("跳过非正式 KnowledgePoint code: %s (name=%s)", point.code, point.name)
            continue
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