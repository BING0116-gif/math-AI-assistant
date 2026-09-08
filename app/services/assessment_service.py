"""Intelligent assessment orchestration.

The LLM may allocate knowledge-point/difficulty quotas only. Question IDs,
bodies, answers and grading remain deterministic PostgreSQL facts.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import (
    AssessmentBlueprint, PracticeSessionDraftAnswer, Chapter, ErrorItem, KnowledgeGraphVersion,
    KnowledgePoint, LearningRecord, PracticeAttempt, PracticeSession,
    PracticeSessionQuestion, Question, QuestionKnowledgePoint, ReviewSchedule,
    UserKnowledgeState,
)
from app.services.llm_service import LLMResponse
from app.services.paper_generator import _grade_one
from app.services.error_classification import classify_error
from app.services.error_review import capture_wrong_attempt
from app.services.practice_service import PracticeError, SUPPORTED_TYPES, _question_snapshot
from app.services.profile_service import get_profile_service
from app.services.session_report import build_session_report

PROMPT_VERSION = "assessment-blueprint-deepseek-v2"
BLUEPRINT_SCHEMA_VERSION = "2"
QUOTA_ORDER = ("weakness", "due_review", "current_chapter", "challenge")
QUOTA_PRESETS = {
    "weakness_check": {"weakness": 0.50, "due_review": 0.20, "current_chapter": 0.20, "challenge": 0.10},
    "stage_retest": {"weakness": 0.35, "due_review": 0.30, "current_chapter": 0.25, "challenge": 0.10},
    "review_due": {"weakness": 0.25, "due_review": 0.50, "current_chapter": 0.15, "challenge": 0.10},
    "comprehensive": {"weakness": 0.30, "due_review": 0.25, "current_chapter": 0.30, "challenge": 0.15},
}
_FORBIDDEN_OUTPUT_KEYS = {"question_id", "question_ids", "content", "question", "answer", "answer_spec", "analysis", "solution"}


class BlueprintBucket(BaseModel):
    quota_kind: Literal["weakness", "due_review", "current_chapter", "challenge"]
    knowledge_point_code: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=30)
    difficulty_min: int = Field(ge=1, le=5)
    difficulty_max: int = Field(ge=1, le=5)
    reason_code: Literal["weak_mastery", "recent_error", "profile_weakness", "coverage", "review_due", "current_chapter", "challenge"]
    reason: str = Field(min_length=1, max_length=160)


class AssessmentPlan(BaseModel):
    buckets: list[BlueprintBucket] = Field(min_length=1, max_length=30)


def quota_counts(goal: str, question_count: int) -> dict[str, int]:
    """Convert a versioned ratio preset to exact integer quotas."""
    preset = QUOTA_PRESETS.get(goal, QUOTA_PRESETS["weakness_check"])
    raw = {kind: preset[kind] * question_count for kind in QUOTA_ORDER}
    result = {kind: int(raw[kind]) for kind in QUOTA_ORDER}
    remaining = question_count - sum(result.values())
    ranked = sorted(QUOTA_ORDER, key=lambda kind: (-(raw[kind] - result[kind]), QUOTA_ORDER.index(kind)))
    for kind in ranked[:remaining]:
        result[kind] += 1
    return result


def _candidate_codes(signals: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, list[str]]:
    available = {row["knowledge_point_code"] for row in inventory if row.get("available", 0) > 0}
    scores = defaultdict(float)
    for skill in signals.get("skills", []):
        scores[skill["code"]] += 1.0 - float(skill.get("mastery", 0))
    for item in signals.get("errors", []):
        for code in item.get("matched_codes", []): scores[code] += min(1.0, item.get("count", 1) * 0.25)
    for item in signals.get("profile_weak_points", []):
        for code in item.get("matched_codes", []): scores[code] += 0.5
    weak = [code for code in sorted(available, key=lambda code: (-scores[code], code)) if scores[code] > 0]
    due = [row["code"] for row in signals.get("due_reviews", []) if row.get("code") in available]
    current = [code for code in signals.get("current_chapter_codes", []) if code in available]
    challenge_mastery = {
        row["code"] for row in signals.get("skills", [])
        if row.get("code") in available and float(row.get("mastery", 0)) >= 0.6
    }
    challenge_inventory = {
        row["knowledge_point_code"] for row in inventory
        if row.get("available_difficulty", {}).get("4", 0) + row.get("available_difficulty", {}).get("5", 0) > 0
    }
    challenge = sorted(challenge_mastery & challenge_inventory)
    return {"weakness": weak, "due_review": list(dict.fromkeys(due)), "current_chapter": current, "challenge": challenge}


def effective_quota_counts(signals: dict[str, Any], inventory: list[dict[str, Any]], question_count: int) -> dict[str, int]:
    """Move unusable category quotas deterministically without losing total count."""
    goal = (signals.get("assessment_request") or {}).get("goal", "weakness_check")
    quotas = quota_counts(goal, question_count)
    candidates = _candidate_codes(signals, inventory)
    fallback_order = {
        "weakness": ("due_review", "current_chapter", "challenge"),
        "due_review": ("weakness", "current_chapter", "challenge"),
        "current_chapter": ("weakness", "due_review", "challenge"),
        "challenge": ("weakness", "due_review", "current_chapter"),
    }
    for kind in QUOTA_ORDER:
        if quotas[kind] and not candidates[kind]:
            target = next((item for item in fallback_order[kind] if candidates[item]), None)
            if target:
                quotas[target] += quotas[kind]
                quotas[kind] = 0
    if sum(quotas.values()) < question_count:
        target = next((kind for kind in QUOTA_ORDER if candidates[kind]), "weakness")
        quotas[target] += question_count - sum(quotas.values())
    return quotas


class DeepSeekAssessmentClient:
    """DeepSeek-only client for assessment blueprint planning."""

    def __init__(self) -> None:
        self.model = settings.DEEPSEEK_MODEL
        self._client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=float(settings.DEEPSEEK_TIMEOUT_SECONDS),
        )

    async def generate(
        self, *, prompt: str, system_prompt: str, model: str,
        temperature: float, max_tokens: int, use_cache: bool = False,
    ) -> LLMResponse:
        del use_cache
        started = asyncio.get_running_loop().time()
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            provider="deepseek",
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
            latency_ms=(asyncio.get_running_loop().time() - started) * 1000,
        )


def is_assessment_ai_available() -> bool:
    return bool(
        settings.AI_ENABLED
        and settings.DEEPSEEK_API_KEY
        and settings.DEEPSEEK_API_KEY.strip()
    )


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(k).lower() in _FORBIDDEN_OUTPUT_KEYS or _contains_forbidden_key(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence: cleaned = fence.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start: raise ValueError("模型未返回 JSON 对象")
    value = json.loads(cleaned[start:end + 1])
    if _contains_forbidden_key(value): raise ValueError("模型输出包含被禁止的题目内容字段")
    return value


class AssessmentBlueprintPlanner:
    def __init__(self, llm: Any | None = None):
        self.llm = llm

    async def plan(self, signals: dict[str, Any], inventory: list[dict[str, Any]], question_count: int) -> dict[str, Any]:
        fallback = self.rule_plan(signals, inventory, question_count)
        expected_quotas = effective_quota_counts(signals, inventory, question_count)
        if not is_assessment_ai_available():
            return {"plan": fallback.model_dump(), "source": "cold_start_rule" if not signals.get("has_history") else "rule_fallback", "model": None, "latency_ms": 0, "token_usage": {}, "error_code": "AI_UNAVAILABLE"}
        system = (
            "你是大学数学检测蓝图规划器。只能基于给定知识点库存和匿名聚合学习信号分配配额。"
            "严禁输出题干、题目ID、答案、解析。必须严格遵守quota_counts。"
            "quota_kind 只能取：weakness, due_review, current_chapter, challenge；"
            "reason_code 只能取：weak_mastery, recent_error, profile_weakness, coverage, review_due, current_chapter, challenge。"
            "只能输出JSON："
            "{\"buckets\":[{quota_kind,knowledge_point_code,count,difficulty_min,difficulty_max,reason_code,reason}]}。"
        )
        prompt = json.dumps({"question_count": question_count, "quota_counts": expected_quotas, "signals": signals, "inventory": inventory}, ensure_ascii=False, separators=(",", ":"))
        try:
            service = self.llm or DeepSeekAssessmentClient()
            response = await asyncio.wait_for(service.generate(prompt=prompt, system_prompt=system, model=settings.DEEPSEEK_MODEL, temperature=0.1, max_tokens=1200, use_cache=False), timeout=8.0)
            raw = _json_object(response.content)
            parsed = AssessmentPlan.model_validate(raw)
            allowed = {row["knowledge_point_code"] for row in inventory}
            if any(bucket.knowledge_point_code not in allowed or bucket.difficulty_min > bucket.difficulty_max for bucket in parsed.buckets):
                raise ValueError("蓝图引用非法知识点或难度范围")
            if sum(bucket.count for bucket in parsed.buckets) != question_count:
                raise ValueError("蓝图题量与请求不一致")
            actual_quotas = {kind: sum(bucket.count for bucket in parsed.buckets if bucket.quota_kind == kind) for kind in QUOTA_ORDER}
            if actual_quotas != expected_quotas:
                raise ValueError("蓝图分类配额与服务端策略不一致")
            if any(bucket.quota_kind == "challenge" and bucket.difficulty_min < 4 for bucket in parsed.buckets):
                raise ValueError("挑战题难度下限必须为4")
            return {"plan": parsed.model_dump(), "source": "llm", "model": response.model, "latency_ms": int(response.latency_ms), "token_usage": response.usage, "error_code": None}
        except Exception as error:
            return {"plan": fallback.model_dump(), "source": "rule_fallback", "model": getattr(self.llm, "model", None), "latency_ms": 0, "token_usage": {}, "error_code": type(error).__name__}

    @staticmethod
    def rule_plan(signals: dict[str, Any], inventory: list[dict[str, Any]], question_count: int) -> AssessmentPlan:
        candidates = _candidate_codes(signals, inventory)
        all_codes = sorted(row["knowledge_point_code"] for row in inventory if row.get("available", 0) > 0)
        if not all_codes: raise PracticeError("INSUFFICIENT_QUESTION_POOL", "当前范围没有可用于智能组卷的正式题目")
        quotas = effective_quota_counts(signals, inventory, question_count)
        buckets = []
        reason_map = {
            "weakness": ("weak_mastery", "根据掌握度、错题和近期表现巩固薄弱点"),
            "due_review": ("review_due", "该知识点已到复习时间"),
            "current_chapter": ("current_chapter", "覆盖当前学习章节"),
            "challenge": ("challenge", "在已有掌握基础上安排进阶挑战"),
        }
        for kind in QUOTA_ORDER:
            count = quotas[kind]
            if not count: continue
            codes = candidates[kind] or all_codes
            per_code = {code: 0 for code in codes}
            for index in range(count): per_code[codes[index % len(codes)]] += 1
            for code, allocated in per_code.items():
                if not allocated: continue
                reason_code, reason = reason_map[kind]
                buckets.append(BlueprintBucket(
                    quota_kind=kind, knowledge_point_code=code, count=allocated,
                    difficulty_min=4 if kind == "challenge" else 1,
                    difficulty_max=5, reason_code=reason_code, reason=reason,
                ))
        return AssessmentPlan(buckets=buckets)


async def _signals(user_id: str, points: list[KnowledgePoint]) -> dict[str, Any]:
    code_by_name = {point.name: point.code for point in points}
    allowed_codes = {point.code for point in points}
    profile_weak: list[dict[str, Any]] = []
    try:
        profile = await get_profile_service().get_profile(user_id)
        for weak in (profile.get("full_profile") or {}).get("weak_points", [])[:10]:
            label = str(weak.get("category") or "")
            matched = [code_by_name[label]] if label in code_by_name else ([label] if label in allowed_codes else [])
            profile_weak.append({"label": label[:80], "mastery": weak.get("mastery"), "matched_codes": matched})
    except Exception:
        pass
    async with get_db_session() as db:
        from app.services.learning_projection import read_learning_states
        skills = sorted((s for s in await read_learning_states(db, user_id) if s.knowledge_point_code in allowed_codes), key=lambda s: s.mastery)[:30]
        due_reviews = list((await db.execute(select(ReviewSchedule).where(ReviewSchedule.user_id == user_id, ReviewSchedule.knowledge_point_code.in_(allowed_codes), ReviewSchedule.due_at <= datetime.now(timezone.utc)).order_by(ReviewSchedule.due_at).limit(30))).scalars())
        errors = list((await db.execute(select(ErrorItem).where(ErrorItem.user_id == user_id, ErrorItem.is_mastered.is_(False)).order_by(ErrorItem.updated_at.desc()).limit(30))).scalars())
        recent = list((await db.execute(select(LearningRecord).where(LearningRecord.user_id == user_id).order_by(LearningRecord.created_at.desc()).limit(50))).scalars())
    normalized_skills = [{"code": s.knowledge_point_code, "mastery": round(float(s.mastery or 0), 3), "attempts": s.attempts_count} for s in skills]
    error_groups: dict[str, int] = defaultdict(int)
    for error in errors:
        labels = list(error.categories or [])
        for label in labels:
            code = code_by_name.get(str(label), str(label) if str(label) in allowed_codes else "")
            if code: error_groups[code] += 1
    point_chapters = {point.code: point.chapter_id for point in points}
    inferred_chapter_id = None
    for record in recent:
        record_codes = list((record.metadata_ or {}).get("knowledge_point_codes") or [])
        inferred_chapter_id = next((point_chapters.get(code) for code in record_codes if point_chapters.get(code)), None)
        if inferred_chapter_id:
            break
    return {
        "has_history": bool(normalized_skills or errors or recent or profile_weak),
        "skills": normalized_skills,
        "errors": [{"count": count, "matched_codes": [code]} for code, count in sorted(error_groups.items())],
        "profile_weak_points": profile_weak,
        "due_reviews": [{"code": row.knowledge_point_code, "due_at": row.due_at.isoformat()} for row in due_reviews],
        "recent_summary": {"attempts": len(recent), "correct": sum(1 for row in recent if row.is_correct is True)},
        "inferred_current_chapter_id": inferred_chapter_id,
        "current_chapter_codes": [point.code for point in points if point.chapter_id == inferred_chapter_id] if inferred_chapter_id else [],
    }


async def readiness(user_id: str, course_id: str | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        filters = [KnowledgeGraphVersion.status == "published"]
        if course_id: filters.append(KnowledgeGraphVersion.course_id == course_id)
        version = (await db.execute(select(KnowledgeGraphVersion).where(*filters).order_by(KnowledgeGraphVersion.created_at.desc()))).scalars().first()
        if not version: raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "没有可用课程版本")
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == version.id))).scalars())
        inventory = await _inventory(db, version.course_id, version.id, {p.code for p in points})
        available_questions = await _available_question_count(db, version.course_id, version.id, {p.code for p in points})
        chapters = list((await db.execute(select(Chapter).where(Chapter.version_id == version.id).order_by(Chapter.sort_order, Chapter.code))).scalars())
    signals = await _signals(user_id, points)
    challenge_points = _candidate_codes(signals, inventory)["challenge"]
    return {
        "course_id": version.course_id, "version_id": version.id,
        "available_questions": available_questions, "max_question_count": min(30, available_questions),
        "knowledge_points": inventory,
        "chapters": [{"id": row.id, "code": row.code, "name": row.name} for row in chapters],
        "inferred_current_chapter_id": signals["inferred_current_chapter_id"],
        "evidence": {
            "has_history": signals["has_history"], "skill_count": len(signals["skills"]),
            "unmastered_error_groups": len(signals["errors"]), "recent_attempts": signals["recent_summary"]["attempts"],
            "weakness_points": len(_candidate_codes(signals, inventory)["weakness"]),
            "due_review_points": len(_candidate_codes(signals, inventory)["due_review"]),
            "current_chapter_points": len(signals["current_chapter_codes"]), "challenge_points": len(challenge_points),
        },
    }


async def _inventory(db, course_id: str, version_id: str, codes: set[str]) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Question.id, Question.difficulty, KnowledgePoint.code, KnowledgePoint.name, KnowledgePoint.chapter_id).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(Question.course_id == course_id, Question.version_id == version_id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.question_type.in_(SUPPORTED_TYPES), KnowledgePoint.code.in_(codes)))).all()
    by_code: dict[str, set[str]] = defaultdict(set)
    metadata: dict[str, dict[str, Any]] = {}
    difficulty: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for qid, level, code, name, chapter_id in rows:
        if qid not in by_code[code]: difficulty[code][str(int(level or 3))] += 1
        by_code[code].add(qid)
        metadata[code] = {"knowledge_point_name": name, "chapter_id": chapter_id}
    return [{
        "knowledge_point_code": code, **metadata[code], "available": len(ids),
        "available_difficulty": dict(difficulty[code]),
    } for code, ids in sorted(by_code.items())]


async def _available_question_count(db, course_id: str, version_id: str, codes: set[str]) -> int:
    ids = (await db.execute(select(Question.id).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(Question.course_id == course_id, Question.version_id == version_id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.question_type.in_(SUPPORTED_TYPES), KnowledgePoint.code.in_(codes)).distinct())).scalars().all()
    return len(ids)


def _assessment_stmt(session_id: str, user_id: str):
    return select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user_id, PracticeSession.mode == "assessment").options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers), selectinload(PracticeSession.blueprint))


def _blueprint_public(blueprint: AssessmentBlueprint | None) -> tuple[Any, dict[str, int], list[dict[str, Any]]]:
    if not blueprint:
        return None, {}, []
    raw = blueprint.blueprint_json or {}
    quotas = {kind: 0 for kind in QUOTA_ORDER}
    for bucket in raw.get("buckets", []):
        kind = bucket.get("quota_kind")
        if kind in quotas: quotas[kind] += int(bucket.get("count", 0))
    return raw, quotas, list(blueprint.deviations_json or [])


def _student_session(session: PracticeSession, include_results: bool = False) -> dict[str, Any]:
    drafts = {d.session_question_id: d for d in session.draft_answers}
    blueprint_summary, quota_summary, deviations = _blueprint_public(session.blueprint)
    base = {"session_id": session.id, "mode": session.mode, "status": session.status, "course_id": session.course_id, "version_id": session.version_id, "duration_limit_seconds": session.duration_limit_seconds, "started_at": session.started_at, "completed_at": session.completed_at, "planning_source": session.blueprint.planning_source if session.blueprint else None, "blueprint_schema_version": session.blueprint.schema_version if session.blueprint else None, "blueprint_summary": blueprint_summary, "quota_summary": quota_summary, "blueprint_deviations": deviations, "questions": []}
    for row in session.questions:
        snap = row.snapshot or {}
        item = {key: snap.get(key) for key in ("question_id", "content", "question_type", "options", "difficulty", "estimated_time", "knowledge_point_codes")}
        item.update({"position": row.position, "score": row.score, "draft_answer": drafts.get(row.id).answer if row.id in drafts else None, "draft_version": drafts.get(row.id).version if row.id in drafts else 0})
        if include_results:
            attempt = next((a for a in session.attempts if a.session_question_id == row.id), None)
            item["result"] = attempt.grading_snapshot if attempt else None
        base["questions"].append(item)
    if include_results:
        base.update(_assessment_result(session))
    return base


def _session_expired(session: PracticeSession) -> bool:
    if not session.started_at or not session.duration_limit_seconds:
        return False
    started = session.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds() >= session.duration_limit_seconds


async def create_assessment(user_id: str, config: dict[str, Any], planner: AssessmentBlueprintPlanner | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        prior = (await db.execute(select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.idempotency_key == config["idempotency_key"]).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers), selectinload(PracticeSession.blueprint)))).scalar_one_or_none()
        if prior:
            if prior.mode != "assessment": raise PracticeError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他模式")
            if prior.config_snapshot != config: raise PracticeError("IDEMPOTENCY_CONFLICT", "该幂等键已用于不同的检测配置")
            return _student_session(prior)
        version = await db.get(KnowledgeGraphVersion, config["version_id"])
        if not version or version.course_id != config["course_id"]: raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程与版本不匹配")
        stmt = select(KnowledgePoint).where(KnowledgePoint.version_id == version.id)
        chapter_ids = set((config.get("scope") or {}).get("chapter_ids") or [])
        if chapter_ids: stmt = stmt.where(KnowledgePoint.chapter_id.in_(chapter_ids))
        points = list((await db.execute(stmt)).scalars())
        if not points: raise PracticeError("VALIDATION_FAILED", "检测范围没有知识点")
        inventory = await _inventory(db, version.course_id, version.id, {p.code for p in points})
    signals = await _signals(user_id, points)
    requested_chapter = config.get("current_chapter_id") or signals.get("inferred_current_chapter_id")
    if requested_chapter:
        if requested_chapter not in {point.chapter_id for point in points}:
            raise PracticeError("VALIDATION_FAILED", "当前章节不属于所选检测范围")
        signals["inferred_current_chapter_id"] = requested_chapter
        signals["current_chapter_codes"] = [point.code for point in points if point.chapter_id == requested_chapter]
    signals["assessment_request"] = {"goal": config["goal"], "intensity": config["intensity"], "duration_minutes": config["duration_minutes"]}
    planned = await (planner or AssessmentBlueprintPlanner()).plan(signals, inventory, config["question_count"])
    plan = AssessmentPlan.model_validate(planned["plan"])
    async with get_db_session() as db:
        seed = config.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1)
        selected, deviations = await _select_questions(db, user_id, version.course_id, version.id, plan, config["question_count"], seed)
        session = PracticeSession(user_id=user_id, mode="assessment", course_id=version.course_id, version_id=version.id, status="created", config_snapshot=config, random_seed=seed, idempotency_key=config["idempotency_key"], duration_limit_seconds=config["duration_minutes"] * 60)
        db.add(session); await db.flush()
        codes = await _question_codes(db, [item[0].id for item in selected])
        for pos, selected_item in enumerate(selected, 1):
            question, bucket, adjustment = selected_item
            snapshot = _question_snapshot(question, codes[question.id])
            snapshot["selection_reason"] = bucket.reason
            snapshot["selection_explanation"] = {
                "quota_kind": bucket.quota_kind, "knowledge_point_code": bucket.knowledge_point_code,
                "evidence_type": bucket.reason_code, "evidence_summary": bucket.reason,
                "adjustment": adjustment,
            }
            db.add(PracticeSessionQuestion(session_id=session.id, question_id=question.id, position=pos, snapshot=snapshot))
        db.add(AssessmentBlueprint(user_id=user_id, session_id=session.id, schema_version=BLUEPRINT_SCHEMA_VERSION, prompt_version=PROMPT_VERSION, model=planned["model"], planning_source=planned["source"], input_signal_snapshot=signals, blueprint_json=plan.model_dump(), deviations_json=deviations, latency_ms=planned["latency_ms"], token_usage=planned["token_usage"], error_code=planned["error_code"]))
        await db.flush()
        loaded = (await db.execute(_assessment_stmt(session.id, user_id))).scalar_one()
        return _student_session(loaded)


async def _select_questions(db, user_id: str, course_id: str, version_id: str, plan: AssessmentPlan, total: int, seed: int):
    codes = {b.knowledge_point_code for b in plan.buckets}
    rows = (await db.execute(select(Question, KnowledgePoint.code).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(Question.course_id == course_id, Question.version_id == version_id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.question_type.in_(SUPPORTED_TYPES), KnowledgePoint.code.in_(codes)))).all()
    buckets: dict[str, list[Question]] = defaultdict(list)
    all_questions: dict[str, Question] = {}
    for q, code in rows: buckets[code].append(q); all_questions[q.id] = q
    recent_ids = set((await db.execute(select(PracticeAttempt.question_id).where(PracticeAttempt.user_id == user_id).order_by(PracticeAttempt.submitted_at.desc()).limit(100))).scalars())
    rng = random.Random(seed); chosen=[]; used=set(); deviations=[]
    for bucket in plan.buckets:
        strict = [q for q in buckets[bucket.knowledge_point_code] if q.id not in recent_ids and q.id not in used and bucket.difficulty_min <= int(q.difficulty or 3) <= bucket.difficulty_max]
        rng.shuffle(strict)
        for question in strict[:bucket.count]: chosen.append((question, bucket, None)); used.add(question.id)
        missing = bucket.count - min(bucket.count, len(strict))
        if missing:
            relaxed = [q for q in buckets[bucket.knowledge_point_code] if q.id not in recent_ids and q.id not in used]
            rng.shuffle(relaxed)
            take = relaxed[:missing]
            for question in take: chosen.append((question, bucket, "difficulty_relaxed")); used.add(question.id)
            if take: deviations.append({"quota_kind": bucket.quota_kind, "knowledge_point_code": bucket.knowledge_point_code, "count": len(take), "reason": "difficulty_relaxed"})
            missing -= len(take)
        if missing:
            same_scope = [q for q in all_questions.values() if q.id not in recent_ids and q.id not in used]
            rng.shuffle(same_scope)
            take = same_scope[:missing]
            for question in take: chosen.append((question, bucket, "knowledge_point_relaxed")); used.add(question.id)
            if take: deviations.append({"quota_kind": bucket.quota_kind, "knowledge_point_code": bucket.knowledge_point_code, "count": len(take), "reason": "knowledge_point_relaxed"})
            missing -= len(take)
        if missing:
            recycled = [q for q in all_questions.values() if q.id not in used]
            rng.shuffle(recycled)
            take = recycled[:missing]
            for question in take: chosen.append((question, bucket, "recent_exposure_reused")); used.add(question.id)
            if take: deviations.append({"quota_kind": bucket.quota_kind, "knowledge_point_code": bucket.knowledge_point_code, "count": len(take), "reason": "recent_exposure_reused"})
    if len(chosen) < total: raise PracticeError("INSUFFICIENT_QUESTION_POOL", "当前检测范围正式题目不足", {"requested": total, "available": len(chosen)})
    rng.shuffle(chosen); return chosen, deviations


async def _question_codes(db, ids: list[str]):
    rows = (await db.execute(select(QuestionKnowledgePoint.question_id, KnowledgePoint.code).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(QuestionKnowledgePoint.question_id.in_(ids)))).all()
    result=defaultdict(list)
    for qid, code in rows: result[qid].append(code)
    return result


async def get_assessment(user_id: str, session_id: str, *, results: bool = False):
    async with get_db_session() as db:
        session=(await db.execute(_assessment_stmt(session_id,user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND","检测会话不存在")
        return _student_session(session, include_results=results and session.status=="completed")


async def start_assessment(user_id: str, session_id: str):
    async with get_db_session() as db:
        session=(await db.execute(_assessment_stmt(session_id,user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND","检测会话不存在")
        if session.status=="created": session.status="in_progress"; session.started_at=datetime.now(timezone.utc)
        elif session.status!="in_progress": raise PracticeError("SESSION_STATE_CONFLICT","检测已结束")
        return _student_session(session)


async def save_draft(user_id: str, session_id: str, question_id: str, answer: Any, expected_version: int):
    async with get_db_session() as db:
        session=(await db.execute(_assessment_stmt(session_id,user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND","检测会话不存在")
        if session.status!="in_progress": raise PracticeError("SESSION_STATE_CONFLICT","检测不在作答状态")
        if _session_expired(session):
            raise PracticeError("SESSION_EXPIRED", "检测时间已结束，请交卷")
        row=next((q for q in session.questions if q.question_id==question_id),None)
        if not row: raise PracticeError("VALIDATION_FAILED","题目不属于当前检测")
        draft=next((d for d in session.draft_answers if d.session_question_id==row.id),None)
        current=draft.version if draft else 0
        if expected_version!=current: raise PracticeError("SESSION_STATE_CONFLICT","答案已在其他设备更新",{"current_version":current})
        if draft: draft.answer=answer; draft.version+=1
        else: draft=PracticeSessionDraftAnswer(user_id=user_id,session_id=session.id,session_question_id=row.id,answer=answer,version=1); db.add(draft)
        await db.flush(); return {"question_id":question_id,"version":draft.version,"saved_at":draft.updated_at}


async def submit_assessment(user_id: str, session_id: str, key: str):
    completed_result = None
    async with get_db_session() as db:
        session=(await db.execute(_assessment_stmt(session_id,user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND","检测会话不存在")
        if session.status=="completed": return _assessment_result(session)
        if session.status!="in_progress": raise PracticeError("SESSION_STATE_CONFLICT","检测尚未开始")
        drafts={d.session_question_id:d for d in session.draft_answers}
        for row in session.questions:
            answer=drafts.get(row.id).answer if row.id in drafts else None
            graded=_grade_one(row.snapshot or {},answer)
            classification=classify_error(row.snapshot or {},answer,correct=graded["correct"])
            snapshot={"question_id":row.question_id,"question_content":(row.snapshot or {}).get("content") or "","your_answer":answer if answer not in (None,"") else "（未作答）","correct":graded["correct"],"needs_review":bool(graded.get("needs_review")),"correct_answer":graded["correct_answer"],"analysis":(row.snapshot or {}).get("analysis") or "","difficulty":(row.snapshot or {}).get("difficulty") or 3,"estimated_time":(row.snapshot or {}).get("estimated_time"),"knowledge_point_codes":(row.snapshot or {}).get("knowledge_point_codes") or [],"selection_reason":(row.snapshot or {}).get("selection_reason"),"selection_explanation":(row.snapshot or {}).get("selection_explanation"),"error_category":classification["category"] if classification else None,"error_classification":classification,"learning_signals":{"attempt_kind":"regular","hint_used":False,"solution_viewed":False}}
            attempt=PracticeAttempt(user_id=user_id,session_id=session.id,session_question_id=row.id,question_id=row.question_id,user_answer=answer,correct=graded["correct"],grading_snapshot=snapshot,idempotency_key=f"{key}:{row.question_id}")
            db.add(attempt)
            if not graded["correct"]:
                await capture_wrong_attempt(
                    db, attempt=attempt, question_snapshot=row.snapshot or {},
                    classification=classification,
                )
            db.add(_learning_record(user_id,row,answer,graded["correct"],graded["correct_answer"],session.id,"assessment"))
        expired = _session_expired(session)
        session.status="completed"; session.completed_at=datetime.now(timezone.utc); session.completion_reason="timeout" if expired else "submitted"
        await db.flush()
        from app.services.learning_projection import rebuild_learning_projections_in_session
        await rebuild_learning_projections_in_session(db, user_id)
        from app.services.outbox import enqueue_outbox
        outbox_event = await enqueue_outbox(
            db, event_type="learning.refresh", aggregate_type="practice_session",
            aggregate_id=session.id, user_id=user_id,
            idempotency_key=f"learning-refresh:assessment:{session.id}",
        )
        await db.flush(); await db.refresh(session, attribute_names=["attempts"])
        completed_result = _assessment_result(session)
    from app.services.outbox import dispatch_outbox_best_effort
    dispatch_outbox_best_effort(outbox_event.id)
    return completed_result


def _learning_record(user_id,row,answer,correct,correct_answer,session_id,mode):
    snap=row.snapshot or {}
    return LearningRecord(user_id=user_id,question_id=row.question_id,event_type="assessment_answer",question_content=snap.get("content") or "",category=(snap.get("knowledge_point_codes") or ["高等数学"])[0],difficulty=snap.get("difficulty") or 3,user_answer=json.dumps(answer,ensure_ascii=False) if not isinstance(answer,str) else answer,correct_answer=str(correct_answer),is_correct=correct,metadata_={"session_id":session_id,"mode":mode,"knowledge_point_codes":snap.get("knowledge_point_codes") or []})


def _assessment_result(session):
    report = build_session_report(
        session,
        planning_source=session.blueprint.planning_source if session.blueprint else None,
    )
    # Assessment GET keeps its established question+result envelope.
    report.pop("questions", None)
    return report
