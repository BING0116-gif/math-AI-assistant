"""Deterministic, owner-bound variant generation for Phase 4.1.

The LLM may eventually suggest a variation dimension through the provider
boundary, but it is never a source of the question answer.  V1 always has a
fully deterministic template fallback.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

import sympy as sp
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    ErrorItem, PracticeSession, PracticeSessionQuestion, Question,
    QuestionKnowledgePoint, VariantGeneration,
)
from app.services.paper_generator import _grade_one

SUPPORTED_TEMPLATES = {"function_value_numeric", "polynomial_expand_expression"}
TEMPLATE_VERSION = "variant-template-v1"
MAX_ATTEMPTS = 8


class VariantGenerationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Candidate:
    content: str
    question_type: str
    answer: str
    answer_spec: dict[str, Any]
    dimensions: list[str]
    parameters: dict[str, Any]


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def validate_blueprint(question: Question) -> dict[str, Any]:
    blueprint = question.variant_blueprint
    if not isinstance(blueprint, dict) or blueprint.get("version") != 1:
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "该题尚未配置可验证的变式模板")
    template = blueprint.get("template")
    expected_type = {
        "function_value_numeric": "numeric_fill",
        "polynomial_expand_expression": "expression_fill",
    }.get(template)
    if template not in SUPPORTED_TEMPLATES or question.question_type != expected_type:
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "该题型或模板不在变式训练 V1 支持范围")
    return blueprint


def is_variant_supported(question: Question | None) -> bool:
    if question is None or question.review_status != "published" or not question.is_active:
        return False
    if question.grading_mode != "deterministic" or not question.auto_grading_eligible:
        return False
    if not question.course_id or not question.version_id:
        return False
    try:
        validate_blueprint(question)
    except VariantGenerationError:
        return False
    return True


def _bounded_pair(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        return default
    low, high = int(value[0]), int(value[1])
    if low > high or low < -20 or high > 20:
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "变式模板参数范围无效")
    return low, high


def _nonzero(rng: random.Random, bounds: tuple[int, int]) -> int:
    values = [value for value in range(bounds[0], bounds[1] + 1) if value != 0]
    if not values:
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "模板范围必须包含非零值")
    return rng.choice(values)


def generate_candidate(blueprint: dict[str, Any], seed: int, requested_dimension: str | None = None) -> Candidate:
    rng = random.Random(seed)
    template = blueprint["template"]
    allowed = list(blueprint.get("variation_dimensions") or ["parameters"])
    if requested_dimension and requested_dimension not in allowed:
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "请求的变化维度不受该模板支持")
    dimension = requested_dimension or rng.choice(allowed)
    bounds = _bounded_pair(blueprint.get("coefficient_range"), (-5, 5))
    variable = str(blueprint.get("variable") or "x")
    if not re.fullmatch(r"[a-zA-Z]", variable):
        raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "模板变量必须是单个拉丁字母")
    x = sp.Symbol(variable)

    if template == "function_value_numeric":
        degree = int(blueprint.get("degree", 2))
        if degree < 1 or degree > 3:
            raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "函数值模板仅支持一至三次多项式")
        coefficients = [_nonzero(rng, bounds)] + [rng.randint(*bounds) for _ in range(degree)]
        input_bounds = _bounded_pair(blueprint.get("input_range"), (-4, 4))
        input_value = rng.randint(*input_bounds)
        expression = sum(coefficient * x ** (degree - index) for index, coefficient in enumerate(coefficients))
        answer = sp.expand(expression).subs(x, input_value)
        if not answer.is_real or not answer.is_finite:
            raise VariantGenerationError("VARIANT_VALIDATION_FAILED", "生成结果不在实数定义域")
        answer_text = str(answer)
        return Candidate(
            content=f"已知 $f({variable})={sp.latex(expression)}$，求 $f({input_value})$。",
            question_type="numeric_fill", answer=answer_text,
            answer_spec={"version": 1, "kind": "numeric_fill", "value": answer_text, "tolerance": 1e-9},
            dimensions=[dimension], parameters={"coefficients": coefficients, "input": input_value, "variable": variable},
        )

    a, b, c, d = _nonzero(rng, bounds), rng.randint(*bounds), _nonzero(rng, bounds), rng.randint(*bounds)
    factored = (a * x + b) * (c * x + d)
    expanded = sp.expand(factored)
    canonical = str(expanded)
    return Candidate(
        content=f"展开并化简 $({sp.latex(a * x + b)})({sp.latex(c * x + d)})$。",
        question_type="expression_fill", answer=canonical,
        answer_spec={"version": 1, "kind": "expression_fill", "canonical": canonical, "variables": [variable]},
        dimensions=[dimension], parameters={"factors": [[a, b], [c, d]], "variable": variable},
    )


def validate_candidate(candidate: Candidate) -> dict[str, Any]:
    graded = _grade_one({"answer_spec": candidate.answer_spec}, candidate.answer)
    if not graded["correct"]:
        raise VariantGenerationError("VARIANT_VALIDATION_FAILED", "生成答案未通过确定性等价验证")
    if not candidate.content.strip() or len(candidate.content) > 4000:
        raise VariantGenerationError("VARIANT_VALIDATION_FAILED", "生成题干为空或过长")
    if candidate.question_type == "expression_fill":
        canonical = sp.sympify(candidate.answer_spec["canonical"])
        if canonical.free_symbols - {sp.Symbol(candidate.answer_spec["variables"][0])}:
            raise VariantGenerationError("VARIANT_VALIDATION_FAILED", "表达式包含模板外变量")
    return {"answer_computed": True, "conditions_checked": True, "equivalence_checked": True, "schema_checked": True}


def candidate_fingerprint(candidate: Candidate) -> str:
    return _hash({"content": _normalize_text(candidate.content), "answer_spec": candidate.answer_spec})


def _payload(row: VariantGeneration) -> dict[str, Any]:
    return {
        "generation_id": row.id,
        "question_id": row.generated_question_id,
        "session_id": row.session_id,
        "status": row.review_status,
        "generation_mode": row.generation_provider,
        "variation_dimensions": row.variation_dimensions,
    }


async def create_variant_session(user_id: str, error_item_key: str, idempotency_key: str, variation_dimension: str | None = None) -> dict[str, Any]:
    request_fingerprint = _hash({"error_id": error_item_key, "variation_dimension": variation_dimension})
    async with get_db_session() as db:
        prior = await db.scalar(select(VariantGeneration).where(
            VariantGeneration.user_id == user_id,
            VariantGeneration.idempotency_key == idempotency_key,
        ))
        if prior:
            if prior.request_fingerprint != request_fingerprint:
                raise VariantGenerationError("IDEMPOTENCY_CONFLICT", "该幂等键已用于不同的变式请求")
            return _payload(prior)

        error_item = await db.scalar(select(ErrorItem).where(
            ErrorItem.user_id == user_id, ErrorItem.item_id == error_item_key,
        ))
        if error_item is None:
            raise VariantGenerationError("ERROR_ITEM_NOT_FOUND", "错题不存在")
        if not error_item.question_id:
            raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "手工错题尚未绑定正式题目")
        source = await db.scalar(select(Question).where(Question.id == error_item.question_id).options(selectinload(Question.knowledge_point_links)))
        if not is_variant_supported(source):
            raise VariantGenerationError("VARIANT_NOT_SUPPORTED", "该错题暂不支持可验证变式")
        blueprint = validate_blueprint(source)

        duplicate_seen = False
        for _ in range(MAX_ATTEMPTS):
            candidate = generate_candidate(blueprint, secrets.randbits(63), variation_dimension)
            report = validate_candidate(candidate)
            fingerprint = candidate_fingerprint(candidate)
            if fingerprint == _hash({"content": _normalize_text(source.content), "answer_spec": source.answer_spec}):
                duplicate_seen = True
                continue
            prior_variant = await db.scalar(select(VariantGeneration.id).where(
                VariantGeneration.user_id == user_id,
                VariantGeneration.duplicate_fingerprint == fingerprint,
            ))
            exact_question = await db.scalar(select(Question.id).where(Question.content == candidate.content, Question.answer == candidate.answer))
            if prior_variant or exact_question:
                duplicate_seen = True
                continue

            question_id = "var-" + uuid.uuid4().hex[:16]
            generated = Question(
                id=question_id, content=candidate.content, question_type=candidate.question_type,
                answer=candidate.answer, answer_spec=candidate.answer_spec,
                analysis="本题由可验证模板生成；提交后按确定性规则判定。",
                category=source.category, sub_categories=source.sub_categories,
                knowledge_points=source.knowledge_points, difficulty=source.difficulty,
                course_id=source.course_id, version_id=source.version_id,
                review_status="draft", is_ai_generated=True, ai_provider="deterministic-template",
                grading_mode="deterministic", practice_eligible=False, exam_eligible=False,
                auto_grading_eligible=True, source=f"variant:{source.id}",
                variant_blueprint=source.variant_blueprint,
            )
            db.add(generated)
            await db.flush()
            for link in source.knowledge_point_links:
                db.add(QuestionKnowledgePoint(question_id=question_id, knowledge_point_id=link.knowledge_point_id, is_primary=link.is_primary))

            session = PracticeSession(
                user_id=user_id, mode="practice", course_id=source.course_id, version_id=source.version_id,
                status="created", random_seed=secrets.randbits(31), idempotency_key=f"variant:{idempotency_key}",
                config_snapshot={
                    "review_kind": "variant_correct", "error_item_id": error_item_key,
                    "source_question_id": source.id, "generation_id": None,
                    "resolved_knowledge_point_codes": list(error_item.knowledge_point_codes or []),
                },
            )
            db.add(session)
            await db.flush()
            db.add(PracticeSessionQuestion(
                session_id=session.id, question_id=question_id, position=1, score=1,
                snapshot={
                    "question_id": question_id, "content": candidate.content,
                    "question_type": candidate.question_type, "options": None,
                    "answer_spec": candidate.answer_spec, "analysis": generated.analysis,
                    "difficulty": generated.difficulty, "estimated_time": generated.estimated_time,
                    "knowledge_point_codes": list(error_item.knowledge_point_codes or []),
                },
            ))
            generation = VariantGeneration(
                user_id=user_id, error_item_id=error_item.id, source_question_id=source.id,
                generated_question_id=question_id, session_id=session.id,
                variation_dimensions=candidate.dimensions, template_version=TEMPLATE_VERSION,
                generation_provider="deterministic-template", generation_model=None, prompt_version=None,
                review_status="draft", validation_report=report | {"parameters": candidate.parameters, "duplicate_checked": True},
                duplicate_fingerprint=fingerprint, idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
            db.add(generation)
            await db.flush()
            session.config_snapshot = dict(session.config_snapshot or {}) | {"generation_id": generation.id}
            return _payload(generation)

        code = "VARIANT_DUPLICATE_EXHAUSTED" if duplicate_seen else "VARIANT_VALIDATION_FAILED"
        raise VariantGenerationError(code, "未能在安全尝试次数内生成有效且不重复的变式")
