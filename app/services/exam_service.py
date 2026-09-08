"""Owner-scoped deterministic exam composition, draft persistence and grading."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import AIInteractionRun, Course, KnowledgeGraphVersion, KnowledgePoint, LearningRecord, PracticeAttempt, PracticeSession, PracticeSessionDraftAnswer, PracticeSessionQuestion, Question, QuestionKnowledgePoint, Chapter
from app.services.error_classification import classify_error
from app.services.error_review import capture_wrong_attempt
from app.services.paper_generator import _grade_one
from app.services.practice_service import PracticeError, SUPPORTED_TYPES, _question_snapshot
from app.services.session_report import build_session_report


def _pool_shortages(requested: dict[str, int], pools: dict[str, list[Question]]) -> dict[str, dict[str, int]]:
    return {kind: {"requested": count, "available": len(pools.get(kind, []))} for kind, count in requested.items() if len(pools.get(kind, [])) < count}


def _stmt(session_id: str, user_id: str, *, lock: bool = False):
    stmt = select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user_id, PracticeSession.mode == "exam").options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers))
    return stmt.with_for_update() if lock else stmt


def _deadline(session: PracticeSession):
    if not session.started_at or not session.duration_limit_seconds: return None
    started = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=timezone.utc)
    return started + timedelta(seconds=session.duration_limit_seconds)


def _expired(session: PracticeSession) -> bool:
    deadline = _deadline(session)
    return bool(deadline and datetime.now(timezone.utc) >= deadline)


def _payload(session: PracticeSession) -> dict[str, Any]:
    drafts = {row.session_question_id: row for row in session.draft_answers}
    return {
        "session_id": session.id, "mode": session.mode, "status": session.status,
        "course_id": session.course_id, "version_id": session.version_id, "config": session.config_snapshot,
        "duration_limit_seconds": session.duration_limit_seconds, "started_at": session.started_at,
        "completed_at": session.completed_at, "completion_reason": session.completion_reason,
        "server_time": datetime.now(timezone.utc), "deadline_at": _deadline(session),
        "questions": [{
            **{key: (row.snapshot or {}).get(key) for key in ("question_id", "content", "question_type", "options", "difficulty", "estimated_time", "knowledge_point_codes")},
            "position": row.position, "draft_answer": drafts[row.id].answer if row.id in drafts else None,
            "draft_version": drafts[row.id].version if row.id in drafts else 0,
        } for row in session.questions],
    }


async def exam_options(course_id: str | None = None) -> dict[str, Any]:
    async with get_db_session() as db:
        course_stmt = select(Course).where(Course.status == "active").order_by(Course.name)
        if course_id: course_stmt = course_stmt.where(Course.id == course_id)
        courses = list((await db.execute(course_stmt)).scalars())
        if not courses: return {"courses": [], "chapters": [], "knowledge_points": [], "question_types": []}
        course = courses[0]
        version = (await db.execute(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.course_id == course.id, KnowledgeGraphVersion.status == "published").order_by(KnowledgeGraphVersion.created_at.desc()))).scalars().first()
        if not version: raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程没有已发布知识版本")
        chapters = list((await db.execute(select(Chapter).where(Chapter.version_id == version.id).order_by(Chapter.sort_order))).scalars())
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.version_id == version.id).order_by(KnowledgePoint.sort_order))).scalars())
        counts = dict((await db.execute(select(Question.question_type, func.count(Question.id)).where(Question.course_id == course.id, Question.version_id == version.id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.grading_mode == "deterministic", Question.question_type.in_(SUPPORTED_TYPES)).group_by(Question.question_type))).all())
        return {"courses": [{"id": row.id, "name": row.name} for row in courses], "course_id": course.id, "version_id": version.id, "chapters": [{"id": row.id, "name": row.name} for row in chapters], "knowledge_points": [{"code": row.code, "name": row.name, "chapter_id": row.chapter_id} for row in points], "question_types": [{"value": kind, "available": int(counts.get(kind, 0))} for kind in sorted(SUPPORTED_TYPES)]}


async def create_exam(user_id: str, config: dict[str, Any]) -> dict[str, Any]:
    key = config["idempotency_key"]
    requested = {kind: int(count) for kind, count in config["question_type_counts"].items() if count}
    async with get_db_session() as db:
        prior = (await db.execute(select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.idempotency_key == key).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers)))).scalar_one_or_none()
        if prior:
            if prior.mode != "exam" or prior.config_snapshot != config: raise PracticeError("IDEMPOTENCY_CONFLICT", "该幂等键已用于其他配置")
            return _payload(prior)
        version = await db.get(KnowledgeGraphVersion, config["version_id"])
        if not version or version.status != "published" or version.course_id != config["course_id"]: raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程与发布版本不匹配")
        point_stmt = select(KnowledgePoint).where(KnowledgePoint.version_id == version.id)
        chapters, codes = set(config.get("chapter_ids") or []), set(config.get("knowledge_point_codes") or [])
        if chapters and codes: point_stmt = point_stmt.where(or_(KnowledgePoint.chapter_id.in_(chapters), KnowledgePoint.code.in_(codes)))
        elif chapters: point_stmt = point_stmt.where(KnowledgePoint.chapter_id.in_(chapters))
        else: point_stmt = point_stmt.where(KnowledgePoint.code.in_(codes))
        points = list((await db.execute(point_stmt)).scalars())
        if not points: raise PracticeError("VALIDATION_FAILED", "考试范围没有有效知识点")
        allowed_codes = {point.code for point in points}
        rows = (await db.execute(select(Question, KnowledgePoint.code).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(Question.course_id == version.course_id, Question.version_id == version.id, Question.review_status == "published", Question.exam_eligible.is_(True), Question.auto_grading_eligible.is_(True), Question.grading_mode == "deterministic", Question.question_type.in_(list(requested)), Question.difficulty >= config["difficulty_min"], Question.difficulty <= config["difficulty_max"], KnowledgePoint.code.in_(allowed_codes)))).all()
        grouped: dict[str, tuple[Question, set[str]]] = {}
        for question, code in rows:
            grouped.setdefault(question.id, (question, set()))[1].add(code)
        pools: dict[str, list[Question]] = defaultdict(list); question_codes: dict[str, list[str]] = {}
        for question, linked in grouped.values(): pools[question.question_type].append(question); question_codes[question.id] = sorted(linked)
        shortages = _pool_shortages(requested, pools)
        if shortages: raise PracticeError("INSUFFICIENT_QUESTION_POOL", "正式题库无法满足题型数量", {"shortages": shortages})
        seed = config.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1); rng = random.Random(seed); selected = []
        for kind, count in sorted(requested.items()): candidates = list(pools[kind]); rng.shuffle(candidates); selected.extend(candidates[:count])
        rng.shuffle(selected)
        session = PracticeSession(user_id=user_id, mode="exam", course_id=version.course_id, version_id=version.id, status="created", config_snapshot=dict(config), random_seed=seed, idempotency_key=key, duration_limit_seconds=config["duration_minutes"] * 60)
        db.add(session); await db.flush()
        for position, question in enumerate(selected, 1): db.add(PracticeSessionQuestion(session_id=session.id, question_id=question.id, position=position, snapshot=_question_snapshot(question, question_codes[question.id])))
        await db.flush(); loaded = (await db.execute(_stmt(session.id, user_id))).scalar_one(); return _payload(loaded)


async def _finalize(db, session: PracticeSession, reason: str) -> None:
    if session.status == "completed": return
    drafts = {row.session_question_id: row for row in session.draft_answers}
    for row in session.questions:
        answer = drafts[row.id].answer if row.id in drafts else None; graded = _grade_one(row.snapshot or {}, answer)
        classification = classify_error(row.snapshot or {}, answer, correct=graded["correct"])
        if answer in (None, "") and not graded["correct"]: classification = {**(classification or {}), "category": "UNANSWERED"}
        result = {"question_id": row.question_id, "question_content": (row.snapshot or {}).get("content") or "", "your_answer": answer if answer not in (None, "") else "（未作答）", "correct": graded["correct"], "needs_review": bool(graded.get("needs_review")), "correct_answer": graded["correct_answer"], "analysis": (row.snapshot or {}).get("analysis") or "", "difficulty": (row.snapshot or {}).get("difficulty") or 3, "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or [], "error_category": classification.get("category") if classification else None, "error_classification": classification, "learning_signals": {"attempt_kind": "regular", "hint_used": False, "solution_viewed": False}}
        attempt = PracticeAttempt(user_id=session.user_id, session_id=session.id, session_question_id=row.id, question_id=row.question_id, user_answer=answer, correct=graded["correct"], grading_snapshot=result, idempotency_key=f"exam-finalize:{session.id}:{row.question_id}")
        db.add(attempt)
        if not graded["correct"]: await capture_wrong_attempt(db, attempt=attempt, question_snapshot=row.snapshot or {}, classification=classification)
        db.add(LearningRecord(user_id=session.user_id, question_id=row.question_id, event_type="exam_answer", question_content=(row.snapshot or {}).get("content") or "", category=((row.snapshot or {}).get("knowledge_point_codes") or ["高等数学"])[0], difficulty=(row.snapshot or {}).get("difficulty") or 3, user_answer=json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str) else answer, correct_answer=str(graded["correct_answer"]), is_correct=graded["correct"], metadata_={"session_id": session.id, "mode": "exam", "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or []}))
    session.status = "completed"; session.completed_at = datetime.now(timezone.utc); session.completion_reason = reason
    await db.flush()
    from app.services.learning_projection import rebuild_learning_projections_in_session
    await rebuild_learning_projections_in_session(db, session.user_id)
    from app.services.outbox import enqueue_outbox
    await enqueue_outbox(
        db, event_type="learning.refresh", aggregate_type="practice_session",
        aggregate_id=session.id, user_id=session.user_id,
        idempotency_key=f"learning-refresh:exam:{session.id}",
    )
    await db.flush(); await db.refresh(session, attribute_names=["attempts"])


async def _refresh_learning(user_id: str) -> None:
    # Compatibility hook: durable outbox events are emitted by _finalize.
    from app.services.outbox import process_outbox_batch
    await process_outbox_batch()


async def get_exam(user_id: str, session_id: str) -> dict[str, Any]:
    finalized = False
    async with get_db_session() as db:
        session = (await db.execute(_stmt(session_id, user_id, lock=True))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "考试会话不存在")
        if session.status == "in_progress" and _expired(session): await _finalize(db, session, "timeout"); finalized = True
        payload = _payload(session)
    if finalized: await _refresh_learning(user_id)
    return payload


async def start_exam(user_id: str, session_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(_stmt(session_id, user_id, lock=True))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "考试会话不存在")
        if session.status == "created": session.status = "in_progress"; session.started_at = datetime.now(timezone.utc)
        elif session.status != "in_progress": raise PracticeError("SESSION_STATE_CONFLICT", "考试已结束")
        return _payload(session)


async def save_exam_draft(user_id: str, session_id: str, question_id: str, answer: Any, expected_version: int) -> dict[str, Any]:
    finalized = False
    async with get_db_session() as db:
        session = (await db.execute(_stmt(session_id, user_id, lock=True))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "考试会话不存在")
        if session.status == "in_progress" and _expired(session): await _finalize(db, session, "timeout"); finalized = True
        if session.status != "in_progress":
            if finalized: result = {"completed": True, "completion_reason": "timeout"}
            else: raise PracticeError("SESSION_STATE_CONFLICT", "考试不在作答状态")
        else:
            row = next((item for item in session.questions if item.question_id == question_id), None)
            if not row: raise PracticeError("VALIDATION_FAILED", "题目不属于当前考试")
            draft = next((item for item in session.draft_answers if item.session_question_id == row.id), None); current = draft.version if draft else 0
            if current != expected_version: raise PracticeError("SESSION_STATE_CONFLICT", "答案已在其他设备更新", {"current_version": current})
            if draft: draft.answer = answer; draft.version += 1
            else: draft = PracticeSessionDraftAnswer(user_id=user_id, session_id=session.id, session_question_id=row.id, answer=answer, version=1); db.add(draft)
            await db.flush(); result = {"question_id": question_id, "version": draft.version, "saved_at": draft.updated_at, "completed": False}
    if finalized: await _refresh_learning(user_id)
    return result


async def submit_exam(user_id: str, session_id: str) -> dict[str, Any]:
    finalized = False
    async with get_db_session() as db:
        session = (await db.execute(_stmt(session_id, user_id, lock=True))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "考试会话不存在")
        if session.status == "completed": return build_session_report(session)
        if session.status != "in_progress": raise PracticeError("SESSION_STATE_CONFLICT", "考试尚未开始")
        await _finalize(db, session, "timeout" if _expired(session) else "submitted"); finalized = True; report = build_session_report(session)
    if finalized: await _refresh_learning(user_id)
    return report


async def exam_report(user_id: str, session_id: str) -> dict[str, Any]:
    await get_exam(user_id, session_id)
    async with get_db_session() as db:
        session = (await db.execute(_stmt(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "考试会话不存在")
        if session.status != "completed": raise PracticeError("SESSION_STATE_CONFLICT", "请先完成考试")
        return build_session_report(session)


async def exam_ai_summary(user_id: str, session_id: str) -> dict[str, Any]:
    """Generate or reuse an optional AI summary (主模型 DeepSeek) grounded only in report facts."""
    import uuid
    from app.dependencies import get_llm_service
    from app.services.ai_capability import is_ai_available
    report = await exam_report(user_id, session_id)
    async with get_db_session() as db:
        cached = (await db.execute(select(AIInteractionRun).where(AIInteractionRun.user_id == user_id, AIInteractionRun.practice_session_id == session_id, AIInteractionRun.request_kind == "exam_report_summary", AIInteractionRun.status == "completed").order_by(AIInteractionRun.created_at.desc()))).scalars().first()
        if cached and cached.output_text: return {"summary": cached.output_text, "cached": True}
    if not is_ai_available(): raise PracticeError("AI_UNAVAILABLE", "AI 总结暂不可用，结构化报告不受影响")
    run_id = str(uuid.uuid4())
    async with get_db_session() as db:
        db.add(AIInteractionRun(id=run_id, user_id=user_id, practice_session_id=session_id, request_kind="exam_report_summary", knowledge_point_codes=[row["knowledge_point_code"] for row in report["knowledge_breakdown"]], prompt_version="exam-report-summary-v1", status="started"))
    facts = {key: report[key] for key in ("score", "max_score", "accuracy", "total", "correct", "duration_seconds", "knowledge_breakdown", "error_breakdown")}
    try:
        response = await get_llm_service().generate(prompt=f"请只依据以下结构化考试事实，用中文写不超过180字的学习总结，指出主要失分模式和一个可执行下一步；不得臆造题目或原因：\n{json.dumps(facts, ensure_ascii=False)}", system_prompt="你是大学数学学习报告助手。结构化事实是唯一依据，证据不足时明确说明。", temperature=0.1, max_tokens=300, use_cache=True)
        content = (response.content or "").strip()
        if not content or len(content) > 1000: raise ValueError("invalid summary")
        async with get_db_session() as db:
            run = await db.get(AIInteractionRun, run_id); run.status = "completed"; run.output_text = content; run.model = response.model; run.latency_ms = int(response.latency_ms); run.token_usage = response.usage or None; run.completed_at = datetime.now(timezone.utc)
        return {"summary": content, "cached": False}
    except Exception as error:
        async with get_db_session() as db:
            run = await db.get(AIInteractionRun, run_id); run.status = "failed"; run.error_code = type(error).__name__; run.completed_at = datetime.now(timezone.utc)
        raise PracticeError("AI_SUMMARY_FAILED", "AI 总结生成失败，可稍后重试")
