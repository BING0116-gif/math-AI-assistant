"""Text-only subjective solution scoring with an auditable, fail-closed contract."""
from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Question, SubjectiveEvaluation
from app.services.llm_service import get_llm_service

PROMPT_VERSION = "subjective-step-score-v1"
DIMENSIONS = ("concept_use", "formula_choice", "derivation_validity", "calculation_correctness", "conclusion_completeness", "expression_quality")
VERDICTS = {"certainly_correct", "probably_correct", "needs_human_review", "unable_to_determine"}

class ScorePayload(BaseModel):
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    verdict: str
    rationale: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "not_required"

def _extract_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if "```" in value:
        value = value.split("```", 2)[1].removeprefix("json").strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start: raise ValueError("评分模型未返回 JSON")
    return json.loads(value[start:end + 1])

def _validate(raw: dict[str, Any]) -> ScorePayload:
    parsed = ScorePayload.model_validate(raw)
    if parsed.verdict not in VERDICTS: raise ValueError("评分结论不在允许集合")
    if parsed.review_status not in {"not_required", "pending", "resolved"}: raise ValueError("复核状态非法")
    scores = {}
    for key, value in parsed.dimension_scores.items():
        if key not in DIMENSIONS: raise ValueError("评分维度非法")
        scores[key] = max(0.0, min(1.0, float(value)))
    parsed.dimension_scores = scores
    if parsed.verdict in {"needs_human_review", "unable_to_determine"}:
        parsed.review_status = "pending"
    return parsed

async def score_text_answer(*, user_id: str, question_id: str, answer: str, idempotency_key: str, attempt_id: str | None = None, llm: Any | None = None) -> dict[str, Any]:
    answer = (answer or "").strip()
    if not answer: raise ValueError("文本答案不能为空")
    async with get_db_session() as db:
        prior = (await db.execute(select(SubjectiveEvaluation).where(SubjectiveEvaluation.user_id == user_id, SubjectiveEvaluation.idempotency_key == idempotency_key))).scalar_one_or_none()
        if prior:
            if prior.question_id != question_id or prior.answer_snapshot != answer: raise ValueError("幂等键已用于其他评分请求")
            return _out(prior)
        question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
        if not question: raise LookupError("题目不存在")
        reference = {"answer": question.answer, "analysis": question.analysis or "", "solution_steps": question.solution_steps or []}
        system = "你是大学数学主观题评分器。只依据题目参考答案和学生文本作答评分，不臆造步骤。必须只输出JSON，字段为 dimension_scores、verdict、rationale、review_status。六个维度必须使用 concept_use、formula_choice、derivation_validity、calculation_correctness、conclusion_completeness、expression_quality，分数0到1。verdict只能是 certainly_correct、probably_correct、needs_human_review、unable_to_determine。证据不足或步骤无法验证时使用 needs_human_review 或 unable_to_determine。"
        prompt = json.dumps({"question": question.content, "reference": reference, "student_answer": answer}, ensure_ascii=False)
        model = None
        try:
            if not settings.AI_ENABLED: raise RuntimeError("AI_DISABLED")
            response = await (llm or get_llm_service()).generate(prompt=prompt, system_prompt=system, temperature=0.0, max_tokens=1200, use_cache=False)
            parsed = _validate(_extract_json(response.content)); model = response.model
        except Exception as exc:
            parsed = ScorePayload(verdict="unable_to_determine", review_status="pending", rationale={"reason":"评分服务不可用或输出无法验证", "error_code": type(exc).__name__}, dimension_scores={})
        row = SubjectiveEvaluation(user_id=user_id, question_id=question_id, attempt_id=attempt_id, answer_snapshot=answer, reference_snapshot=reference, dimension_scores=parsed.dimension_scores, verdict=parsed.verdict, rationale=parsed.rationale, review_status=parsed.review_status, model=model, prompt_version=PROMPT_VERSION, idempotency_key=idempotency_key)
        db.add(row); await db.flush(); return _out(row)

def _out(row: SubjectiveEvaluation) -> dict[str, Any]:
    return {"evaluation_id": row.id, "question_id": row.question_id, "attempt_id": row.attempt_id, "dimension_scores": row.dimension_scores, "verdict": row.verdict, "rationale": row.rationale, "review_status": row.review_status, "model": row.model, "prompt_version": row.prompt_version, "created_at": row.created_at}
