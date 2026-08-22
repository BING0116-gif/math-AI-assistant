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
    AssessmentBlueprint, AssessmentDraftAnswer, ErrorItem, KnowledgeGraphVersion,
    KnowledgePoint, LearningRecord, PracticeAttempt, PracticeSession,
    PracticeSessionQuestion, Question, QuestionKnowledgePoint, ReviewSchedule,
    UserKnowledgeState,
)
from app.services.llm_service import LLMResponse
from app.services.paper_generator import _grade_one
from app.services.practice_service import PracticeError, SUPPORTED_TYPES, _question_snapshot
from app.services.profile_service import get_profile_service

PROMPT_VERSION = "assessment-blueprint-deepseek-v1"
_FORBIDDEN_OUTPUT_KEYS = {"question_id", "question_ids", "content", "question", "answer", "answer_spec", "analysis", "solution"}


class BlueprintBucket(BaseModel):
    knowledge_point_code: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=30)
    difficulty_min: int = Field(ge=1, le=5)
    difficulty_max: int = Field(ge=1, le=5)
    reason_code: Literal["weak_mastery", "recent_error", "profile_weakness", "coverage", "review_due"]
    reason: str = Field(min_length=1, max_length=160)


class AssessmentPlan(BaseModel):
    buckets: list[BlueprintBucket] = Field(min_length=1, max_length=30)


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
        if not is_assessment_ai_available():
            return {"plan": fallback.model_dump(), "source": "cold_start_rule" if not signals.get("has_history") else "rule_fallback", "model": None, "latency_ms": 0, "token_usage": {}, "error_code": "AI_UNAVAILABLE"}
        system = (
            "你是大学数学检测蓝图规划器。只能基于给定知识点库存和匿名聚合学习信号分配配额。"
            "严禁输出题干、题目ID、答案、解析。只能输出JSON：{\"buckets\":[{knowledge_point_code,count,difficulty_min,difficulty_max,reason_code,reason}]}。"
        )
        prompt = json.dumps({"question_count": question_count, "signals": signals, "inventory": inventory}, ensure_ascii=False, separators=(",", ":"))
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
            return {"plan": parsed.model_dump(), "source": "llm", "model": response.model, "latency_ms": int(response.latency_ms), "token_usage": response.usage, "error_code": None}
        except Exception as error:
            return {"plan": fallback.model_dump(), "source": "rule_fallback", "model": getattr(self.llm, "model", None), "latency_ms": 0, "token_usage": {}, "error_code": type(error).__name__}

    @staticmethod
    def rule_plan(signals: dict[str, Any], inventory: list[dict[str, Any]], question_count: int) -> AssessmentPlan:
        scores = defaultdict(float)
        for skill in signals.get("skills", []): scores[skill["code"]] += 1.0 - float(skill.get("mastery", 0))
        for item in signals.get("errors", []):
            for code in item.get("matched_codes", []): scores[code] += min(1.0, item.get("count", 1) * 0.25)
        for item in signals.get("profile_weak_points", []):
            for code in item.get("matched_codes", []): scores[code] += 0.5
        for item in signals.get("due_reviews", []): scores[item["code"]] += 1.25
        available = {row["knowledge_point_code"]: row["available"] for row in inventory if row["available"] > 0}
        ordered = sorted(available, key=lambda code: (-scores[code], code))
        if not ordered: raise PracticeError("INSUFFICIENT_QUESTION_POOL", "当前范围没有可用于智能检测的正式题目")
        counts = {code: 0 for code in ordered}
        for index in range(question_count): counts[ordered[index % len(ordered)]] += 1
        buckets = []
        for code in ordered:
            if not counts[code]: continue
            reason_code = "review_due" if any(row.get("code") == code for row in signals.get("due_reviews", [])) else ("weak_mastery" if scores[code] else "coverage")
            buckets.append(BlueprintBucket(knowledge_point_code=code, count=counts[code], difficulty_min=1, difficulty_max=5, reason_code=reason_code, reason="优先检测薄弱知识点" if scores[code] else "保证范围覆盖"))
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
        skills = list((await db.execute(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id, UserKnowledgeState.knowledge_point_code.in_(allowed_codes)).order_by(UserKnowledgeState.mastery).limit(30))).scalars())
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
    return {
        "has_history": bool(normalized_skills or errors or recent or profile_weak),
        "skills": normalized_skills,
        "errors": [{"count": count, "matched_codes": [code]} for code, count in sorted(error_groups.items())],
        "profile_weak_points": profile_weak,
        "due_reviews": [{"code": row.knowledge_point_code, "due_at": row.due_at.isoformat()} for row in due_reviews],
        "recent_summary": {"attempts": len(recent), "correct": sum(1 for row in recent if row.is_correct is True)},
    }


async def readiness(user_id: str, course_id: str | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        filters = [KnowledgeGraphVersion.status == "published"]
        if course_id: filters.append(KnowledgeGraphVersion.course_id == course_id)
        version = (await db.execute(select(KnowledgeGraphVersion).where(*filters).order_by(KnowledgeGraphVersion.created_at.desc()))).scalars().first()
        if not version: raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "没有可用课程版本")
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == version.id))).scalars())
        inventory = await _inventory(db, version.course_id, version.id, {p.code for p in points})
    signals = await _signals(user_id, points)
    return {"course_id": version.course_id, "version_id": version.id, "available_questions": sum(row["available"] for row in inventory), "knowledge_points": inventory, "evidence": {"has_history": signals["has_history"], "skill_count": len(signals["skills"]), "unmastered_error_groups": len(signals["errors"]), "recent_attempts": signals["recent_summary"]["attempts"]}}


async def _inventory(db, course_id: str, version_id: str, codes: set[str]) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Question.id, KnowledgePoint.code).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(Question.course_id == course_id, Question.version_id == version_id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.question_type.in_(SUPPORTED_TYPES), KnowledgePoint.code.in_(codes)))).all()
    by_code: dict[str, set[str]] = defaultdict(set)
    for qid, code in rows: by_code[code].add(qid)
    return [{"knowledge_point_code": code, "available": len(ids)} for code, ids in sorted(by_code.items())]


def _assessment_stmt(session_id: str, user_id: str):
    return select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user_id, PracticeSession.mode == "assessment").options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers), selectinload(PracticeSession.blueprint))


def _student_session(session: PracticeSession, include_results: bool = False) -> dict[str, Any]:
    drafts = {d.session_question_id: d for d in session.draft_answers}
    base = {"session_id": session.id, "mode": session.mode, "status": session.status, "course_id": session.course_id, "version_id": session.version_id, "duration_limit_seconds": session.duration_limit_seconds, "started_at": session.started_at, "completed_at": session.completed_at, "planning_source": session.blueprint.planning_source if session.blueprint else None, "blueprint_summary": session.blueprint.blueprint_json if session.blueprint else None, "questions": []}
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
    signals["assessment_request"] = {"goal": config["goal"], "intensity": config["intensity"], "duration_minutes": config["duration_minutes"]}
    planned = await (planner or AssessmentBlueprintPlanner()).plan(signals, inventory, config["question_count"])
    plan = AssessmentPlan.model_validate(planned["plan"])
    async with get_db_session() as db:
        seed = config.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1)
        selected, deviations = await _select_questions(db, user_id, version.course_id, version.id, plan, config["question_count"], seed)
        session = PracticeSession(user_id=user_id, mode="assessment", course_id=version.course_id, version_id=version.id, status="created", config_snapshot=config, random_seed=seed, idempotency_key=config["idempotency_key"], duration_limit_seconds=config["duration_minutes"] * 60)
        db.add(session); await db.flush()
        codes = await _question_codes(db, [q.id for q in selected])
        reasons = {b.knowledge_point_code: b for b in plan.buckets}
        for pos, question in enumerate(selected, 1):
            snapshot = _question_snapshot(question, codes[question.id]); snapshot["selection_reason"] = next((reasons[c].reason for c in codes[question.id] if c in reasons), "保证范围覆盖")
            db.add(PracticeSessionQuestion(session_id=session.id, question_id=question.id, position=pos, snapshot=snapshot))
        db.add(AssessmentBlueprint(user_id=user_id, session_id=session.id, prompt_version=PROMPT_VERSION, model=planned["model"], planning_source=planned["source"], input_signal_snapshot=signals, blueprint_json=plan.model_dump(), deviations_json=deviations, latency_ms=planned["latency_ms"], token_usage=planned["token_usage"], error_code=planned["error_code"]))
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
        candidates = [q for q in buckets[bucket.knowledge_point_code] if q.id not in recent_ids and bucket.difficulty_min <= int(q.difficulty or 3) <= bucket.difficulty_max]
        rng.shuffle(candidates); take = [q for q in candidates if q.id not in used][:bucket.count]
        chosen.extend(take); used.update(q.id for q in take)
        if len(take) < bucket.count: deviations.append({"knowledge_point_code": bucket.knowledge_point_code, "requested": bucket.count, "selected": len(take), "reason": "inventory_shortfall"})
    remainder = [q for q in all_questions.values() if q.id not in recent_ids]; rng.shuffle(remainder)
    chosen.extend([q for q in remainder if q.id not in used][:total-len(chosen)])
    if len(chosen) < total:
        recycled = list(all_questions.values()); rng.shuffle(recycled)
        chosen.extend([q for q in recycled if q.id not in used][:total-len(chosen)])
        if chosen and recent_ids: deviations.append({"reason": "recent_exposure_reused", "count": len([q for q in chosen if q.id in recent_ids])})
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
        else: draft=AssessmentDraftAnswer(user_id=user_id,session_id=session.id,session_question_id=row.id,answer=answer,version=1); db.add(draft)
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
            snapshot={"question_id":row.question_id,"question_content":(row.snapshot or {}).get("content") or "","your_answer":answer if answer not in (None,"") else "（未作答）","correct":graded["correct"],"correct_answer":graded["correct_answer"],"analysis":(row.snapshot or {}).get("analysis") or "","knowledge_point_codes":(row.snapshot or {}).get("knowledge_point_codes") or [],"selection_reason":(row.snapshot or {}).get("selection_reason"),"error_category":None if graded["correct"] else ("unanswered" if answer in (None,"") else "answer_mismatch")}
            attempt=PracticeAttempt(user_id=user_id,session_id=session.id,session_question_id=row.id,question_id=row.question_id,user_answer=answer,correct=graded["correct"],grading_snapshot=snapshot,idempotency_key=f"{key}:{row.question_id}")
            db.add(attempt); db.add(_learning_record(user_id,row,answer,graded["correct"],graded["correct_answer"],session.id,"assessment"))
        expired = _session_expired(session)
        session.status="completed"; session.completed_at=datetime.now(timezone.utc); session.completion_reason="timeout" if expired else "submitted"
        await db.flush(); await db.refresh(session, attribute_names=["attempts"])
        completed_result = _assessment_result(session)
    from app.services.learning_projection import refresh_learning_projections_safely
    await refresh_learning_projections_safely(user_id)
    await get_profile_service().incremental_update(user_id)
    return completed_result


def _learning_record(user_id,row,answer,correct,correct_answer,session_id,mode):
    snap=row.snapshot or {}
    return LearningRecord(user_id=user_id,question_id=row.question_id,event_type="assessment_answer",question_content=snap.get("content") or "",category=(snap.get("knowledge_point_codes") or ["高等数学"])[0],difficulty=snap.get("difficulty") or 3,user_answer=json.dumps(answer,ensure_ascii=False) if not isinstance(answer,str) else answer,correct_answer=str(correct_answer),is_correct=correct,metadata_={"session_id":session_id,"mode":mode,"knowledge_point_codes":snap.get("knowledge_point_codes") or []})


def _assessment_result(session):
    items=[a.grading_snapshot for a in sorted(session.attempts,key=lambda a: next((q.position for q in session.questions if q.id==a.session_question_id),999))]
    by_code=defaultdict(lambda:{"total":0,"correct":0})
    for item in items:
        for code in item.get("knowledge_point_codes") or []: by_code[code]["total"]+=1;by_code[code]["correct"]+=int(item["correct"])
    weakest=sorted(by_code,key=lambda code:(by_code[code]["correct"]/by_code[code]["total"],code))[:3]
    errors=defaultdict(int)
    for item in items:
        if not item.get("correct"): errors[item.get("error_category") or "unanswered"]+=1
    started=session.started_at.replace(tzinfo=timezone.utc) if session.started_at and session.started_at.tzinfo is None else session.started_at
    completed=session.completed_at.replace(tzinfo=timezone.utc) if session.completed_at and session.completed_at.tzinfo is None else session.completed_at
    elapsed=max(0,int((completed-started).total_seconds())) if started and completed else None
    return {"session_id":session.id,"status":session.status,"planning_source":session.blueprint.planning_source,"total":len(items),"correct":sum(int(i["correct"]) for i in items),"duration_seconds":elapsed,"results":items,"knowledge_breakdown":[{"knowledge_point_code":code,**value,"accuracy":round(value["correct"]/value["total"],3)} for code,value in sorted(by_code.items())],"error_breakdown":[{"category":code,"count":count} for code,count in sorted(errors.items())],"next_practice_config":{"course_id":session.course_id,"version_id":session.version_id,"knowledge_point_codes":weakest,"question_count":min(10,max(5,len(items)))} if weakest else None}
