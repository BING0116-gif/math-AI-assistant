"""Deterministic, SQL-only orchestration for the student practice mode.

This module deliberately has no dependency on Agent, profile, error-book, Redis,
or Qdrant services.  The database remains the sole source of questions and of
the resulting learning facts.
"""
from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, LearningRecord, PracticeAttempt,
    PracticeSession, PracticeSessionQuestion, Question, QuestionKnowledgePoint,
)
from app.services.paper_generator import _grade_one
from app.services.error_classification import classify_error
from app.services.error_review import capture_wrong_attempt

SUPPORTED_TYPES = {"choice", "judge", "numeric_fill", "expression_fill"}


class PracticeError(Exception):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra or {}


def _question_snapshot(question: Question, kp_codes: list[str]) -> dict[str, Any]:
    return {
        "question_id": question.id, "content": question.content,
        "question_type": question.question_type, "options": question.options,
        "answer_spec": question.answer_spec, "analysis": question.analysis,
        "common_mistakes": question.common_mistakes,
        "difficulty": question.difficulty, "estimated_time": question.estimated_time,
        "knowledge_point_codes": kp_codes,
    }


def _student_question(row: PracticeSessionQuestion) -> dict[str, Any]:
    snap = row.snapshot or {}
    return {key: snap.get(key) for key in ("question_id", "content", "question_type", "options", "difficulty", "estimated_time", "knowledge_point_codes")} | {"position": row.position, "score": row.score}


def _session_statement(session_id: str, user_id: str):
    return select(PracticeSession).where(
        PracticeSession.id == session_id, PracticeSession.user_id == user_id,
        PracticeSession.mode == "practice",
    ).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts))


def _session_payload(session: PracticeSession) -> dict[str, Any]:
    attempts = {a.session_question_id: a for a in session.attempts}
    return {
        "session_id": session.id, "mode": session.mode, "status": session.status,
        "course_id": session.course_id, "version_id": session.version_id,
        "config": session.config_snapshot, "started_at": session.started_at,
        "completed_at": session.completed_at,
        "questions": [
            _student_question(question) | {"attempted": question.id in attempts}
            for question in session.questions
        ],
        # Practice feedback is available only for already committed answers.
        # Returning it here makes a refresh recover the exact submitted state
        # without exposing material for unanswered questions.
        "feedback": {attempt.question_id: attempt.grading_snapshot for attempt in session.attempts},
    }


async def practice_options(course_id: str | None = None) -> dict[str, Any]:
    """Return metadata only; never return a question body or answer."""
    async with get_db_session() as db:
        courses = list((await db.execute(select(Course).where(Course.status == "active").order_by(Course.name))).scalars())
        if course_id is None and courses:
            course_id = courses[0].id
        if not course_id:
            return {"courses": [], "chapters": [], "knowledge_points": [], "question_types": []}
        course = await db.get(Course, course_id)
        if course is None:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程不可用")
        version_id = course.default_version_id
        if not version_id:
            version_id = (await db.execute(select(KnowledgeGraphVersion.id).where(KnowledgeGraphVersion.course_id == course_id).order_by(KnowledgeGraphVersion.created_at.desc()))).scalar()
        if not version_id:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程尚未发布知识版本")
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id, KnowledgePoint.version_id == version_id).order_by(KnowledgePoint.name))).scalars())
        chapters = list((await db.execute(select(Chapter).where(Chapter.course_id == course_id, Chapter.version_id == version_id).order_by(Chapter.sort_order, Chapter.name))).scalars())
        counts = dict((await db.execute(
            select(Question.question_type, func.count(Question.id)).where(
                Question.review_status == "published", Question.practice_eligible.is_(True),
                Question.grading_mode == "deterministic", Question.question_type.in_(SUPPORTED_TYPES),
                Question.course_id == course_id, Question.version_id == version_id,
            ).group_by(Question.question_type)
        )).all())
        return {
            "courses": [{"id": c.id, "name": c.name, "default_version_id": c.default_version_id} for c in courses],
            "course_id": course_id, "version_id": version_id,
            "chapters": [{"id": c.id, "name": c.name, "parent_id": c.parent_id, "level": c.level} for c in chapters],
            "knowledge_points": [{"code": p.code, "name": p.name, "chapter_id": p.chapter_id} for p in points],
            "question_types": [{"value": kind, "available": counts.get(kind, 0)} for kind in sorted(SUPPORTED_TYPES)],
        }


async def create_session(user_id: str, config: dict[str, Any]) -> dict[str, Any]:
    course_id, version_id = config["course_id"], config["version_id"]
    chapter_ids = set(config.get("chapter_ids") or [])
    explicit_codes = set(config.get("knowledge_point_codes") or [])
    question_types = set(config.get("question_types") or SUPPORTED_TYPES)
    count = config["question_count"]
    difficulty = config.get("difficulty_band")
    seed = config.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1)
    key = config["idempotency_key"]
    if not chapter_ids and not explicit_codes:
        raise PracticeError("VALIDATION_FAILED", "至少选择一个章节或知识点")
    if not question_types or not question_types <= SUPPORTED_TYPES:
        raise PracticeError("VALIDATION_FAILED", "包含不支持的题型")
    async with get_db_session() as db:
        prior = (await db.execute(_session_statement_by_key(user_id, key))).scalar_one_or_none()
        if prior:
            prior_config = dict(prior.config_snapshot or {})
            prior_config.pop("random_seed", None)
            prior_config.pop("resolved_knowledge_point_codes", None)
            if prior_config != config:
                raise PracticeError("IDEMPOTENCY_CONFLICT", "该幂等键已用于不同的练习配置")
            return _session_payload(prior)
        version = await db.get(KnowledgeGraphVersion, version_id)
        if version is None or version.course_id != course_id:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程与知识版本不匹配")
        if config.get("review_schedule_id"):
            from app.data.models import ReviewSchedule
            schedule = await db.scalar(select(ReviewSchedule).where(
                ReviewSchedule.id == config["review_schedule_id"],
                ReviewSchedule.user_id == user_id,
            ))
            if schedule is None:
                raise PracticeError("VALIDATION_FAILED", "复习计划不存在或不属于当前用户")
            if explicit_codes != {schedule.knowledge_point_code}:
                raise PracticeError("VALIDATION_FAILED", "绑定练习必须只覆盖复习计划对应知识点")
            config["review_interval_days"] = schedule.interval_days
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id, KnowledgePoint.version_id == version_id))).scalars())
        by_code = {p.code: p for p in points}
        chosen_codes = set(explicit_codes)
        if chapter_ids:
            valid_chapters = {p.chapter_id for p in points}
            if not chapter_ids <= valid_chapters:
                raise PracticeError("VALIDATION_FAILED", "所选章节不属于当前课程版本")
            chapter_codes = {p.code for p in points if p.chapter_id in chapter_ids}
            if explicit_codes and not explicit_codes <= chapter_codes:
                raise PracticeError("VALIDATION_FAILED", "所选知识点不属于所选章节")
            chosen_codes |= chapter_codes
        if not chosen_codes or not chosen_codes <= set(by_code):
            raise PracticeError("VALIDATION_FAILED", "所选知识点不属于当前课程版本")
        stmt = select(Question, KnowledgePoint.code).join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(
            Question.review_status == "published", Question.practice_eligible.is_(True),
            Question.grading_mode == "deterministic", Question.question_type.in_(question_types),
            Question.course_id == course_id, Question.version_id == version_id, KnowledgePoint.code.in_(chosen_codes),
        )
        if difficulty:
            stmt = stmt.where(Question.difficulty.between(difficulty[0], difficulty[1]))
        rows = (await db.execute(stmt)).all()
        questions: dict[str, Question] = {}
        question_codes: dict[str, list[str]] = defaultdict(list)
        for question, code in rows:
            questions[question.id] = question
            question_codes[question.id].append(code)
        if len(questions) < count:
            raise PracticeError("INSUFFICIENT_QUESTION_POOL", "当前筛选条件下正式题目不足", {"requested": count, "available": len(questions), "suggestions": [{"action": "reduce_count", "value": max(5, len(questions))}]})
        selected = _balanced_select(list(questions.values()), question_codes, count, seed)
        stored_config = dict(config) | {"random_seed": seed, "resolved_knowledge_point_codes": sorted(chosen_codes)}
        session = PracticeSession(user_id=user_id, mode="practice", course_id=course_id, version_id=version_id, status="created", config_snapshot=stored_config, random_seed=seed, idempotency_key=key)
        db.add(session)
        await db.flush()
        for position, question in enumerate(selected, 1):
            db.add(PracticeSessionQuestion(session_id=session.id, question_id=question.id, position=position, snapshot=_question_snapshot(question, question_codes[question.id])))
        await db.flush()
        loaded = (await db.execute(_session_statement(session.id, user_id))).scalar_one()
        return _session_payload(loaded)


async def create_session_from_questions(
    user_id: str,
    question_ids: list[str],
    course_id: str,
    version_id: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a practice session from an explicit list of question IDs.

    This is the bridge between the adaptive RAG recommender and the
    practice-taking UI: unlike create_session (manual filter + balanced
    sampling), this path takes a concrete list of IDs and preserves their
    order. Only questions that are published, practice-eligible,
    deterministically gradable, of a supported type and belonging to the given
    course/version are kept; the rest are silently dropped.
    """
    ids = [str(i) for i in (question_ids or []) if i]
    if not ids:
        raise PracticeError("VALIDATION_FAILED", "未提供题目ID")
    async with get_db_session() as db:
        rows = (await db.execute(
            select(Question, KnowledgePoint.code)
            .join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .where(
                Question.id.in_(ids),
                Question.review_status == "published",
                Question.practice_eligible.is_(True),
                Question.grading_mode == "deterministic",
                Question.question_type.in_(SUPPORTED_TYPES),
                Question.course_id == course_id,
                Question.version_id == version_id,
            )
        )).all()
        questions: dict[str, Question] = {}
        question_codes: dict[str, list[str]] = defaultdict(list)
        for question, code in rows:
            questions[question.id] = question
            question_codes[question.id].append(code)
        if not questions:
            raise PracticeError(
                "INSUFFICIENT_QUESTION_POOL",
                "推荐题目均不可用于练习（可能题型不支持自动判分或未发布）",
                {"requested": len(ids), "available": 0},
            )
        ordered = [questions[i] for i in ids if i in questions]
        seed = random.SystemRandom().randint(1, 2**31 - 1)
        base = dict(config or {})
        key = base.pop("idempotency_key", None) or f"rag-session-{uuid.uuid4().hex[:16]}"
        stored_config = base | {
            "selection": "rag",
            "source_question_ids": list(questions),
            "random_seed": seed,
        }
        session = PracticeSession(
            user_id=user_id, mode="practice", course_id=course_id, version_id=version_id,
            status="created", config_snapshot=stored_config, random_seed=seed,
            idempotency_key=key,
        )
        db.add(session)
        await db.flush()
        for position, question in enumerate(ordered, 1):
            db.add(PracticeSessionQuestion(
                session_id=session.id, question_id=question.id, position=position,
                snapshot=_question_snapshot(question, question_codes[question.id]),
            ))
        await db.flush()
        loaded = (await db.execute(_session_statement(session.id, user_id))).scalar_one()
        return _session_payload(loaded)


def _session_statement_by_key(user_id: str, key: str):
    return select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.idempotency_key == key).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts))


def _balanced_select(questions: list[Question], codes: dict[str, list[str]], count: int, seed: int) -> list[Question]:
    rng = random.Random(seed)
    buckets: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        for code in codes[question.id]:
            buckets[code].append(question)
    for bucket in buckets.values(): rng.shuffle(bucket)
    chosen: list[Question] = []
    used: set[str] = set()
    while len(chosen) < count:
        progressed = False
        for code in sorted(buckets):
            candidate = next((q for q in buckets[code] if q.id not in used), None)
            if candidate:
                chosen.append(candidate); used.add(candidate.id); progressed = True
                if len(chosen) == count: break
        if not progressed: break
    return chosen


async def get_session(user_id: str, session_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        return _session_payload(session)


async def start_session(user_id: str, session_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        if session.status == "created":
            session.status, session.started_at = "in_progress", datetime.now(timezone.utc)
        elif session.status != "in_progress":
            raise PracticeError("SESSION_STATE_CONFLICT", "会话已结束")
        return _session_payload(session)


async def submit_attempt(user_id: str, session_id: str, question_id: str, answer: Any, key: str, learning_signals: dict[str, Any] | None = None) -> dict[str, Any]:
    committed_result = None
    category = ""
    outbox_ids: list[str] = []
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        if session.status != "in_progress": raise PracticeError("SESSION_STATE_CONFLICT", "会话尚未开始或已结束")
        row = next((q for q in session.questions if q.question_id == question_id), None)
        if not row: raise PracticeError("VALIDATION_FAILED", "题目不属于该练习会话")
        attempt = next((a for a in session.attempts if a.session_question_id == row.id), None)
        if attempt:
            if attempt.idempotency_key != key: raise PracticeError("ANSWER_ALREADY_COMMITTED", "该题已提交")
            return attempt.grading_snapshot
        graded = _grade_one(row.snapshot or {}, answer)
        from app.observability import GRADING_RESULTS
        outcome = "needs_review" if graded.get("needs_review") else ("correct" if graded.get("correct") else "incorrect")
        GRADING_RESULTS.labels(outcome).inc()
        classification = classify_error(row.snapshot or {}, answer, correct=graded["correct"])
        session_context = session.config_snapshot or {}
        attempt_kind = {
            "original_correct": "original_retry", "variant_correct": "variant",
            "spaced_correct": "spaced_review",
        }.get(session_context.get("review_kind"), "regular")
        signals = dict(learning_signals or {})
        signals["attempt_kind"] = attempt_kind
        if session_context.get("review_interval_days") is not None:
            signals["review_interval_days"] = session_context["review_interval_days"]
        result = {"question_id": question_id, "question_content": (row.snapshot or {}).get("content") or "", "correct": graded["correct"], "needs_review": bool(graded.get("needs_review")), "correct_answer": graded["correct_answer"], "analysis": (row.snapshot or {}).get("analysis") or "", "difficulty": (row.snapshot or {}).get("difficulty") or 3, "estimated_time": (row.snapshot or {}).get("estimated_time"), "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or [], "error_category": classification["category"] if classification else None, "error_classification": classification, "learning_signals": signals}
        practice_attempt = PracticeAttempt(user_id=user_id, session_id=session.id, session_question_id=row.id, question_id=question_id, user_answer=answer, correct=graded["correct"], grading_snapshot=result, idempotency_key=key)
        db.add(practice_attempt)
        await db.flush()
        result["attempt_id"] = practice_attempt.id
        practice_attempt.grading_snapshot = result
        if not graded["correct"]:
            await capture_wrong_attempt(
                db, attempt=practice_attempt, question_snapshot=row.snapshot or {},
                classification=classification,
            )
        db.add(LearningRecord(
            user_id=user_id, question_id=question_id, event_type="practice_answer",
            question_content=(row.snapshot or {}).get("content") or "",
            category=((row.snapshot or {}).get("knowledge_point_codes") or ["高等数学"])[0],
            difficulty=(row.snapshot or {}).get("difficulty") or 3,
            user_answer=json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str) else answer,
            correct_answer=str(graded["correct_answer"]), is_correct=graded["correct"],
            metadata_={"session_id": session.id, "attempt_id": practice_attempt.id, "learning_signals": signals, "needs_review": bool(graded.get("needs_review")), "mode": "practice", "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or []},
        ))
        committed_result = result
        category = ((row.snapshot or {}).get("knowledge_point_codes") or [""])[0]
        await db.flush()
        from app.services.learning_projection import rebuild_learning_projections_in_session
        await rebuild_learning_projections_in_session(db, user_id)
        from app.services.outbox import enqueue_outbox
        refresh = await enqueue_outbox(
            db, event_type="learning.refresh", aggregate_type="practice_attempt",
            aggregate_id=practice_attempt.id, user_id=user_id, payload={"category": category},
            idempotency_key=f"learning-refresh:attempt:{practice_attempt.id}",
        )
        outbox_ids.append(refresh.id)
        if committed_result.get("correct") and session_context.get("review_schedule_id"):
            review = await enqueue_outbox(
                db, event_type="review.complete", aggregate_type="practice_attempt",
                aggregate_id=practice_attempt.id, user_id=user_id,
                payload={"review_schedule_id": int(session_context["review_schedule_id"]), "attempt_id": practice_attempt.id},
                idempotency_key=f"auto-review:{practice_attempt.id}",
            )
            outbox_ids.append(review.id)
    from app.services.outbox import dispatch_outbox_best_effort
    for event_id in outbox_ids:
        dispatch_outbox_best_effort(event_id)
    return committed_result


async def complete_session(user_id: str, session_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        if session.status == "completed": return await _result_for(session)
        if session.status != "in_progress": raise PracticeError("SESSION_STATE_CONFLICT", "会话尚未开始")
        session.status, session.completed_at = "completed", datetime.now(timezone.utc)
        return await _result_for(session)


async def result(user_id: str, session_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        if session.status != "completed": raise PracticeError("SESSION_STATE_CONFLICT", "请先完成练习")
        return await _result_for(session)


async def _result_for(session: PracticeSession) -> dict[str, Any]:
    attempts = {a.session_question_id: a for a in session.attempts}
    items = []
    correct = 0
    breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for row in session.questions:
        attempt = attempts.get(row.id)
        if attempt:
            item = attempt.grading_snapshot
        else:
            classification = classify_error(row.snapshot or {}, None, correct=False)
            item = {"question_id": row.question_id, "correct": False, "your_answer": "（未作答）", "correct_answer": (row.snapshot or {}).get("answer_spec", {}).get("correct"), "analysis": (row.snapshot or {}).get("analysis") or "", "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or [], "error_category": classification["category"], "error_classification": classification}
        items.append(item)
        correct += int(bool(item["correct"]))
        for code in item.get("knowledge_point_codes") or []:
            breakdown[code]["total"] += 1; breakdown[code]["correct"] += int(bool(item["correct"]))
    weakest = sorted(breakdown, key=lambda code: (breakdown[code]["correct"] / breakdown[code]["total"], code))[:3]
    elapsed = _elapsed_seconds(session.started_at, session.completed_at)
    errors: dict[str, int] = defaultdict(int)
    for item in items:
        if not item.get("correct"): errors[item.get("error_category") or "UNKNOWN"] += 1
    return {"session_id": session.id, "status": session.status, "total": len(session.questions), "completed": len(attempts), "correct": correct, "duration_seconds": elapsed, "results": items, "knowledge_breakdown": [{"knowledge_point_code": c, **v, "accuracy": round(v["correct"] / v["total"], 3)} for c, v in sorted(breakdown.items())], "error_breakdown": [{"category": category, "count": count} for category, count in sorted(errors.items())], "next_practice_config": {"course_id": session.course_id, "version_id": session.version_id, "knowledge_point_codes": weakest, "question_count": min(10, max(5, len(session.questions)))} if weakest else None}


async def recent_sessions(user_id: str, limit: int = 8) -> dict[str, Any]:
    # Listing recent exams is also a server-authoritative deadline check.
    async with get_db_session() as db:
        active_exam_ids = list((await db.execute(select(PracticeSession.id).where(
            PracticeSession.user_id == user_id,
            PracticeSession.mode == "exam",
            PracticeSession.status == "in_progress",
        ).limit(limit))).scalars())
    if active_exam_ids:
        from app.services.exam_service import get_exam
        for session_id in active_exam_ids:
            await get_exam(user_id, session_id)
    async with get_db_session() as db:
        sessions = list((await db.execute(select(PracticeSession).where(PracticeSession.user_id == user_id).order_by(PracticeSession.updated_at.desc()).limit(limit).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts), selectinload(PracticeSession.draft_answers)))).scalars())
    rows = []
    for session in sessions:
        prefix = "assessment" if session.mode == "assessment" else "exam" if session.mode == "exam" else "practice"
        result_suffix = "report" if session.mode == "exam" else "result"
        answered = len(session.draft_answers) if session.mode == "exam" else len(session.attempts)
        rows.append({"session_id": session.id, "mode": session.mode, "status": session.status, "total": len(session.questions), "answered": answered, "correct": sum(int(a.correct) for a in session.attempts), "updated_at": session.updated_at, "result_path": f"/apply/{prefix}/sessions/{session.id}/{result_suffix}" if session.status == "completed" else None, "resume_path": f"/apply/{prefix}/sessions/{session.id}" if session.status != "completed" else None})
    return {"unfinished": [row for row in rows if row["status"] != "completed"], "completed": [row for row in rows if row["status"] == "completed"]}


def _elapsed_seconds(started: datetime | None, completed: datetime | None) -> int | None:
    if not started or not completed: return None
    if started.tzinfo is None: started = started.replace(tzinfo=timezone.utc)
    if completed.tzinfo is None: completed = completed.replace(tzinfo=timezone.utc)
    return max(0, int((completed - started).total_seconds()))
