"""§5.3 参数化变式题模板服务（PrairieLearn generate() 模式）。

纯确定性参数采样（random.Random(seed)，同 seed 完全可复现）→ {{param}} 模板渲染
→ safe_math/sympy 求值固化 answer_spec（复用现有判分契约，判分端零改动）。

安全边界：模板生成题必须先"试生成 + 人工抽检"（review_status=published）后才能
进入组卷候选池；retired 一键下架只阻止后续实例化，已生成题与快照不受影响。
审计与去重：生成题 Question.source=f"template:{id}"，variant_blueprint 固化
参数指纹（同模板同参数组合不重复落库）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    KnowledgePoint, Question, QuestionKnowledgePoint, QuestionTemplate,
)
from app.services.safe_math import SafeExpressionError, parse_safe_expression

logger = logging.getLogger(__name__)

TEMPLATE_QUESTION_TYPES = {"choice", "judge", "numeric_fill", "expression_fill"}
TEMPLATE_REVIEW_STATUSES = {"draft", "reviewed", "published", "retired"}
# 采样去重：同模板寻找未用参数组合的最大尝试次数
MAX_SAMPLING_ATTEMPTS = 24
# 每个已发布模板在选题池合并时的默认实例化上限
POOL_PER_TEMPLATE_LIMIT = 3


class QuestionTemplateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ── 参数 schema 校验与采样 ──
def validate_params_schema(schema: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(schema, dict) or not schema:
        raise QuestionTemplateError("VALIDATION_FAILED", "params_schema 必须为非空对象")
    if len(schema) > 12:
        raise QuestionTemplateError("VALIDATION_FAILED", "参数数量最多 12 个")
    normalized: dict[str, dict[str, Any]] = {}
    for name, spec in schema.items():
        if not isinstance(name, str) or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise QuestionTemplateError("VALIDATION_FAILED", f"参数名不合法：{name}")
        if not isinstance(spec, dict):
            raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 定义必须是对象")
        ptype = spec.get("type")
        if ptype == "int":
            rng = spec.get("range")
            if not isinstance(rng, (list, tuple)) or len(rng) != 2:
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 需要 range: [min, max]")
            lo, hi = int(rng[0]), int(rng[1])
            if lo > hi or abs(lo) > 10**6 or abs(hi) > 10**6:
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 取值范围不合法")
            normalized[name] = {"type": "int", "range": [lo, hi]}
        elif ptype == "float":
            rng = spec.get("range")
            if not isinstance(rng, (list, tuple)) or len(rng) != 2:
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 需要 range: [min, max]")
            lo, hi = float(rng[0]), float(rng[1])
            if lo > hi or not (-1e6 <= lo <= 1e6 and -1e6 <= hi <= 1e6):
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 取值范围不合法")
            precision = int(spec.get("precision", 2))
            if not (0 <= precision <= 6):
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} precision 必须在 0..6")
            normalized[name] = {"type": "float", "range": [lo, hi], "precision": precision}
        elif ptype == "enum":
            values = spec.get("values")
            if not isinstance(values, list) or not values or len(values) > 12:
                raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 需要 1..12 个枚举值")
            normalized[name] = {"type": "enum", "values": values}
        else:
            raise QuestionTemplateError("VALIDATION_FAILED", f"参数 {name} 类型必须是 int/float/enum")
    return normalized


def sample_params(schema: dict[str, dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    """按 schema 确定性采样一组参数。"""
    params: dict[str, Any] = {}
    for name, spec in schema.items():
        if spec["type"] == "int":
            params[name] = rng.randint(spec["range"][0], spec["range"][1])
        elif spec["type"] == "float":
            params[name] = round(rng.uniform(spec["range"][0], spec["range"][1]), spec.get("precision", 2))
        else:
            params[name] = rng.choice(spec["values"])
    return params


# ── 模板渲染 ──
def render_template(text: str, params: dict[str, Any]) -> str:
    rendered = str(text or "")
    for name, value in params.items():
        rendered = rendered.replace("{{" + name + "}}", _param_text(value))
    if "{{" in rendered and "}}" in rendered:
        leftover = rendered[rendered.index("{{"):rendered.index("}}") + 2]
        raise QuestionTemplateError("VALIDATION_FAILED", f"模板包含未知占位符 {leftover}")
    return rendered


def _param_text(value: Any) -> str:
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def params_fingerprint(template_id: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"t": template_id, "p": {k: params[k] for k in sorted(params)}}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


# ── 答案固化（safe_math 求值 → answer_spec，判分契约不变）──
def build_answer_spec(question_type: str, rendered_answer: str, variables: list[str] | None = None) -> dict[str, Any]:
    # choice/judge 的答案是选项 id / 布尔，不是数学表达式，跳过 sympy 求值
    if question_type == "choice":
        return {"version": 1, "kind": "choice", "correct": str(rendered_answer).strip()}
    if question_type == "judge":
        return {"version": 1, "kind": "judge", "correct": str(rendered_answer).strip().lower() in ("true", "对", "√", "1", "yes")}
    try:
        expr = parse_safe_expression(rendered_answer, variables or [])
    except SafeExpressionError as exc:
        raise QuestionTemplateError("ANSWER_EVALUATION_FAILED", f"答案模板无法求值：{exc}") from exc
    import sympy
    simplified = sympy.simplify(expr)
    if question_type == "numeric_fill":
        value = simplified.evalf(12)
        if not value.is_real:
            raise QuestionTemplateError("ANSWER_EVALUATION_FAILED", "数值题答案必须是实数")
        number = float(value)
        if abs(number - round(number)) < 1e-9:
            number = int(round(number))
        else:
            number = round(number, 6)
        return {"version": 1, "kind": "numeric_fill", "value": number}
    if question_type == "expression_fill":
        return {"version": 1, "kind": "expression_fill", "canonical": str(simplified), "variables": list(variables or [])}
    raise QuestionTemplateError("VALIDATION_FAILED", f"模板不支持题型 {question_type}")


# ── 单次实例化（渲染 + 校验，不落库）──
def render_one_instance(template: QuestionTemplate, params: dict[str, Any]) -> dict[str, Any]:
    """渲染一个模板实例：题干 / 选项 / 固化 answer_spec / 指纹。"""
    body = render_template(template.body_template, params)
    answer_text = render_template(template.answer_template, params)
    variables = list((template.params_schema or {}).get("__variables__") or [])
    answer_spec = build_answer_spec(template.question_type, answer_text, variables)
    options = None
    if template.question_type == "choice":
        if not isinstance(template.options_template, list) or not template.options_template:
            raise QuestionTemplateError("VALIDATION_FAILED", "choice 模板必须提供 options_template")
        options = []
        for option in template.options_template:
            options.append({"id": str(option.get("id", "")), "text": render_template(str(option.get("text", "")), params)})
        if str(answer_spec.get("correct")) not in {str(option["id"]) for option in options}:
            raise QuestionTemplateError("ANSWER_EVALUATION_FAILED", "choice 模板正确答案不在选项中")
    return {
        "body": body,
        "answer_text": answer_text,
        "answer_spec": answer_spec,
        "options": options,
        "fingerprint": params_fingerprint(template.id, params),
        "params": dict(params),
    }


def sample_preview(template: QuestionTemplate, count: int = 10, seed: int | None = None) -> list[dict[str, Any]]:
    """试生成样例（人工抽检用，不落库）。默认 seed=0，保证同模板抽检可复现。"""
    schema = validate_params_schema(template.params_schema)
    rng = random.Random(seed if seed is not None else 0)
    previews: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts = 0
    limit = max(1, min(int(count), 30))
    while len(previews) < limit and attempts < limit * MAX_SAMPLING_ATTEMPTS:
        attempts += 1
        params = sample_params(schema, rng)
        fingerprint = params_fingerprint(template.id, params)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        previews.append(render_one_instance(template, params))
    if not previews:
        raise QuestionTemplateError("SAMPLING_EXHAUSTED", "参数空间过小，无法生成不重复样例")
    return previews


# ── 落库实例化（组卷候选池合并入口）──
async def materialize_pool(
    course_id: str | None,
    version_id: str | None,
    qtypes: list[str],
    kp_codes: list[str],
    seed: int,
    per_template_limit: int = POOL_PER_TEMPLATE_LIMIT,
) -> list[Question]:
    """把已发布模板实例化为正式题（published）并返回，与题库直选题合并成候选池。

    确定性：同一 (模板, seed, 已生成数) 生成相同参数序列；参数指纹去重防止
    同模板同参数组合重复落库。蓝图不变：模板题带知识点与难度参与配额分配。
    """
    wanted_types = [q for q in qtypes if q in TEMPLATE_QUESTION_TYPES]
    if not wanted_types:
        return []
    async with get_db_session() as db:
        stmt = select(QuestionTemplate).where(
            QuestionTemplate.review_status == "published",
            QuestionTemplate.question_type.in_(wanted_types),
        ).order_by(QuestionTemplate.created_at)
        if version_id:
            stmt = stmt.where(QuestionTemplate.version_id == version_id)
        elif course_id:
            stmt = stmt.where(QuestionTemplate.course_id == course_id)
        templates = list((await db.execute(stmt)).scalars())
        if not templates:
            return []
        # 该课程版本下 code -> knowledge_point_id 映射（建立生成题的知识点关联）；
        # 按首个模板的 course/version 解析（同一池内模板属于同一范围）
        scope_course, scope_version = templates[0].course_id, templates[0].version_id
        kp_rows = (await db.execute(select(KnowledgePoint.id, KnowledgePoint.code).where(
            KnowledgePoint.course_id == scope_course, KnowledgePoint.version_id == scope_version,
        ))).all()
        kp_id_by_code = {code: pid for pid, code in kp_rows}
        if kp_codes:
            templates = [t for t in templates if set(t.knowledge_point_codes or []) & set(kp_codes)]
        generated: list[Question] = []
        for template in templates:
            schema = validate_params_schema(template.params_schema)
            prior_rows = (await db.execute(
                select(Question.variant_blueprint).where(Question.source == f"template:{template.id}")
            )).scalars()
            used_fingerprints = {(row or {}).get("fingerprint") for row in prior_rows}
            link_ids = [kp_id_by_code[c] for c in (template.knowledge_point_codes or []) if c in kp_id_by_code]
            if not link_ids:
                logger.warning("[题目模板] 模板 %s 知识点映射缺失，跳过", template.id)
                continue
            rng = random.Random(f"{seed}:{template.id}:{len(used_fingerprints)}")
            produced = 0
            attempts = 0
            while produced < per_template_limit and attempts < per_template_limit * MAX_SAMPLING_ATTEMPTS:
                attempts += 1
                params = sample_params(schema, rng)
                fingerprint = params_fingerprint(template.id, params)
                if fingerprint in used_fingerprints:
                    continue
                try:
                    instance = render_one_instance(template, params)
                except QuestionTemplateError as exc:
                    logger.warning("[题目模板] 实例化失败 template=%s: %s", template.id, exc.message)
                    break
                question_id = "qt-" + uuid.uuid4().hex[:16]
                question = Question(
                    id=question_id, content=instance["body"], question_type=template.question_type,
                    answer=str(instance["answer_text"]), answer_spec=instance["answer_spec"],
                    options=instance["options"], analysis="本题由已审核的参数化模板确定性生成。",
                    category=(template.knowledge_point_codes or ["模板变式"])[0],
                    difficulty=template.difficulty, course_id=template.course_id, version_id=template.version_id,
                    review_status="published", grading_mode="deterministic",
                    practice_eligible=True, exam_eligible=True, auto_grading_eligible=True,
                    is_ai_generated=False, ai_provider="question-template",
                    source=f"template:{template.id}",
                    variant_blueprint={"template_id": template.id, "params": instance["params"], "fingerprint": fingerprint},
                )
                db.add(question)
                await db.flush()
                for position, kp_id in enumerate(link_ids):
                    db.add(QuestionKnowledgePoint(question_id=question_id, knowledge_point_id=kp_id, is_primary=position == 0))
                generated.append(question)
                used_fingerprints.add(fingerprint)
                produced += 1
            if produced:
                template.generation_count = int(template.generation_count or 0) + produced
                template.last_generated_at = datetime.now(timezone.utc)
        if generated:
            await db.flush()
            # 重新带知识点关系加载，供下游 _kp_codes_map / 快照使用
            reloaded = (await db.execute(
                select(Question).where(Question.id.in_([q.id for q in generated])).options(selectinload(Question.knowledge_point_links))
            )).scalars().all()
            return list(reloaded)
    return []


# ── admin CRUD / 状态机 ──
async def create_template(admin_user_id: str, payload: dict[str, Any]) -> QuestionTemplate:
    from app.data.models import Course, KnowledgeGraphVersion
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 120:
        raise QuestionTemplateError("VALIDATION_FAILED", "name 必须为 1..120 字符")
    question_type = str(payload.get("question_type") or "")
    if question_type not in TEMPLATE_QUESTION_TYPES:
        raise QuestionTemplateError("VALIDATION_FAILED", f"question_type 必须是 {sorted(TEMPLATE_QUESTION_TYPES)} 之一")
    validate_params_schema(payload.get("params_schema"))
    body_template = str(payload.get("body_template") or "").strip()
    answer_template = str(payload.get("answer_template") or "").strip()
    if not body_template or not answer_template:
        raise QuestionTemplateError("VALIDATION_FAILED", "body_template / answer_template 不能为空")
    if question_type == "choice" and not isinstance(payload.get("options_template"), list):
        raise QuestionTemplateError("VALIDATION_FAILED", "choice 模板必须提供 options_template 列表")
    knowledge_point_codes = [str(c) for c in (payload.get("knowledge_point_codes") or [])]
    if not knowledge_point_codes:
        raise QuestionTemplateError("VALIDATION_FAILED", "至少关联一个知识点")
    difficulty = int(payload.get("difficulty") or 3)
    if not (1 <= difficulty <= 5):
        raise QuestionTemplateError("VALIDATION_FAILED", "difficulty 必须在 1..5")
    async with get_db_session() as db:
        course_id, version_id = str(payload["course_id"]), str(payload["version_id"])
        version = await db.get(KnowledgeGraphVersion, version_id)
        if version is None or version.course_id != course_id:
            raise QuestionTemplateError("VALIDATION_FAILED", "课程与知识版本不匹配")
        points = (await db.execute(select(KnowledgePoint.code).where(
            KnowledgePoint.course_id == course_id, KnowledgePoint.version_id == version_id,
            KnowledgePoint.code.in_(knowledge_point_codes),
        ))).scalars().all()
        if set(points) != set(knowledge_point_codes):
            raise QuestionTemplateError("VALIDATION_FAILED", "知识点不属于当前课程版本")
        # __variables__ 是 answer_spec 的变量声明（expression_fill 含未知量时使用）
        schema = dict(payload["params_schema"])
        variables = [str(v) for v in (payload.get("variables") or [])]
        if variables:
            schema["__variables__"] = variables
        template = QuestionTemplate(
            id=str(uuid.uuid4()), course_id=course_id, version_id=version_id,
            base_question_id=payload.get("base_question_id") or None,
            name=name, question_type=question_type,
            params_schema=schema, body_template=body_template, answer_template=answer_template,
            options_template=payload.get("options_template") if question_type == "choice" else None,
            knowledge_point_codes=knowledge_point_codes, difficulty=difficulty,
            review_status="draft", created_by=admin_user_id,
            notes=payload.get("notes") or None,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template


async def get_template(template_id: str) -> QuestionTemplate:
    async with get_db_session() as db:
        template = await db.get(QuestionTemplate, template_id)
        if template is None:
            raise QuestionTemplateError("NOT_FOUND", "题目模板不存在")
        return template


async def list_templates(course_id: str | None = None, status: str | None = None) -> list[QuestionTemplate]:
    async with get_db_session() as db:
        stmt = select(QuestionTemplate).order_by(QuestionTemplate.created_at.desc()).limit(200)
        if course_id:
            stmt = stmt.where(QuestionTemplate.course_id == course_id)
        if status:
            if status not in TEMPLATE_REVIEW_STATUSES:
                raise QuestionTemplateError("VALIDATION_FAILED", "无效的状态过滤")
            stmt = stmt.where(QuestionTemplate.review_status == status)
        return list((await db.execute(stmt)).scalars())


async def set_template_status(template_id: str, action: str) -> QuestionTemplate:
    """状态机：publish（draft/reviewed → published，需已通过试生成抽检）、retire（任意 → retired）。"""
    async with get_db_session() as db:
        template = await db.get(QuestionTemplate, template_id)
        if template is None:
            raise QuestionTemplateError("NOT_FOUND", "题目模板不存在")
        if action == "publish":
            if template.review_status not in ("draft", "reviewed"):
                raise QuestionTemplateError("STATE_CONFLICT", "仅 draft/reviewed 模板可发布")
            template.review_status = "published"
        elif action == "retire":
            if template.review_status == "retired":
                return template
            template.review_status = "retired"
        else:
            raise QuestionTemplateError("VALIDATION_FAILED", "action 必须是 publish/retire")
        await db.commit()
        await db.refresh(template)
        return template


def serialize_template(template: QuestionTemplate) -> dict[str, Any]:
    return {
        "id": template.id, "name": template.name,
        "course_id": template.course_id, "version_id": template.version_id,
        "base_question_id": template.base_question_id,
        "question_type": template.question_type,
        "params_schema": template.params_schema,
        "body_template": template.body_template, "answer_template": template.answer_template,
        "options_template": template.options_template,
        "knowledge_point_codes": template.knowledge_point_codes,
        "difficulty": template.difficulty, "review_status": template.review_status,
        "generation_count": template.generation_count,
        "last_generated_at": template.last_generated_at.isoformat() if template.last_generated_at else None,
        "notes": template.notes,
        "created_at": template.created_at.isoformat() if template.created_at else None,
    }
