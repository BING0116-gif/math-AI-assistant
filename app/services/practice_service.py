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
    Chapter, Course, ErrorItem, KnowledgeGraphVersion, KnowledgePoint, LearningRecord, PracticeAttempt,
    PracticeSession, PracticeSessionQuestion, Question, QuestionKnowledgePoint,
)
from app.services.paper_generator import _grade_one
from app.services.error_classification import classify_error
from app.services.error_review import capture_wrong_attempt

SUPPORTED_TYPES = {"choice", "multi_choice", "judge", "numeric_fill", "expression_fill"}
# ---- §5.1 答题行为配置（Moodle-style behaviour）：仅影响放行/重试/反馈时序，不改判分事实 ----
SUPPORTED_BEHAVIORS = {"immediate", "adaptive", "deferred"}
SUPPORTED_ORDER_MODES = {"sequential", "random"}
# immediate：答错可重试一次（共 2 次提交）；adaptive：按次衰减共 3 次提交；deferred：每题一次，统一反馈
BEHAVIOR_MAX_SUBMISSIONS = {"immediate": 2, "adaptive": 3, "deferred": 1}
# adaptive 衰减仅进入 learning_signals.mastery_weight（掌握度投影加权），判分事实不变
ADAPTIVE_MASTERY_WEIGHTS = (1.0, 0.6, 0.3)
ERROR_BOOK_MAX_QUESTIONS = 50


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
    return {key: snap.get(key) for key in ("question_id", "content", "question_type", "options", "difficulty", "estimated_time", "knowledge_point_codes", "common_mistakes")} | {"position": row.position, "score": row.score}


def _session_statement(session_id: str, user_id: str):
    return select(PracticeSession).where(
        PracticeSession.id == session_id, PracticeSession.user_id == user_id,
        PracticeSession.mode == "practice",
    ).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts))


def _session_payload(session: PracticeSession) -> dict[str, Any]:
    attempts = {a.session_question_id: a for a in session.attempts}
    behavior = str((session.config_snapshot or {}).get("behavior") or "immediate")
    defer_feedback = behavior == "deferred" and session.status != "completed"
    feedback: dict[str, Any] = {}
    for attempt in session.attempts:
        if defer_feedback:
            # deferred 练习在完成前不泄露任何判分信息（模拟考试语义），仅暴露已提交状态。
            feedback[attempt.question_id] = {"question_id": attempt.question_id, "submitted": True, "feedback_deferred": True}
        else:
            feedback[attempt.question_id] = attempt.grading_snapshot
    return {
        "session_id": session.id, "mode": session.mode, "status": session.status,
        "course_id": session.course_id, "version_id": session.version_id,
        "config": session.config_snapshot, "started_at": session.started_at,
        "completed_at": session.completed_at,
        "recovery_snapshot": session.recovery_snapshot or {},
        "recovery_snapshot_at": session.recovery_snapshot_at,
        "questions": [
            _student_question(question) | {"attempted": question.id in attempts}
            for question in session.questions
        ],
        # Practice feedback is available only for already committed answers.
        # Returning it here makes a refresh recover the exact submitted state
        # without exposing material for unanswered questions.
        "feedback": feedback,
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


def _config_for_key_compare(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize a config dict for idempotency comparison.

    Server-injected keys are dropped, and behavior/order_mode defaults are
    treated as absent so pre-refactor requests replay against upgraded ones.
    """
    normalized = dict(config)
    normalized.pop("random_seed", None)
    normalized.pop("resolved_knowledge_point_codes", None)
    if normalized.get("behavior") in (None, "immediate"):
        normalized.pop("behavior", None)
    if normalized.get("order_mode") in (None, "random"):
        normalized.pop("order_mode", None)
    if normalized.get("review_policy") in (None, "immediate"):
        normalized.pop("review_policy", None)
    if "shuffle_options" not in normalized or normalized.get("shuffle_options") is False:
        normalized.pop("shuffle_options", None)
    return normalized


def apply_options_shuffle(snapshot: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """§5.4 选项乱序：服务端打乱 choice/multi_choice 选项展示顺序并快照标记。

    选项内容与 id 绑定不变，判分按 id 进行，因此乱序不影响判分；
    ``options_shuffled`` 标记供前端识别与报告端说明。
    """
    options = snapshot.get("options")
    if snapshot.get("question_type") in ("choice", "multi_choice") and isinstance(options, list) and len(options) > 1:
        shuffled = list(options)
        rng.shuffle(shuffled)
        snapshot["options"] = shuffled
        snapshot["options_shuffled"] = True
    return snapshot


async def create_session(user_id: str, config: dict[str, Any]) -> dict[str, Any]:
    course_id, version_id = config["course_id"], config["version_id"]
    chapter_ids = set(config.get("chapter_ids") or [])
    explicit_codes = set(config.get("knowledge_point_codes") or [])
    question_types = set(config.get("question_types") or SUPPORTED_TYPES)
    count = config["question_count"]
    difficulty = config.get("difficulty_band")
    behavior = str(config.get("behavior") or "immediate")
    order_mode = str(config.get("order_mode") or "random")
    seed = config.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1)
    key = config["idempotency_key"]
    if not chapter_ids and not explicit_codes:
        raise PracticeError("VALIDATION_FAILED", "至少选择一个章节或知识点")
    if not question_types or not question_types <= SUPPORTED_TYPES:
        raise PracticeError("VALIDATION_FAILED", "包含不支持的题型")
    if behavior not in SUPPORTED_BEHAVIORS:
        raise PracticeError("VALIDATION_FAILED", "不支持的答题行为")
    if order_mode not in SUPPORTED_ORDER_MODES:
        raise PracticeError("VALIDATION_FAILED", "不支持的排序方式")
    async with get_db_session() as db:
        prior = (await db.execute(_session_statement_by_key(user_id, key))).scalar_one_or_none()
        if prior:
            if _config_for_key_compare(prior.config_snapshot or {}) != _config_for_key_compare(config):
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
        selected = _balanced_select(list(questions.values()), question_codes, count, seed, order_mode)
        stored_config = dict(config) | {"behavior": behavior, "order_mode": order_mode, "random_seed": seed, "resolved_knowledge_point_codes": sorted(chosen_codes)}
        session = PracticeSession(user_id=user_id, mode="practice", course_id=course_id, version_id=version_id, status="created", config_snapshot=stored_config, random_seed=seed, idempotency_key=key)
        db.add(session)
        await db.flush()
        shuffle_options = bool(config.get("shuffle_options", False))
        option_rng = random.Random(seed ^ 0x5EED)
        for position, question in enumerate(selected, 1):
            snapshot = _question_snapshot(question, question_codes[question.id])
            if shuffle_options: apply_options_shuffle(snapshot, option_rng)
            db.add(PracticeSessionQuestion(session_id=session.id, question_id=question.id, position=position, snapshot=snapshot))
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
        base = dict(config or {})
        key = base.pop("idempotency_key", None) or f"rag-session-{uuid.uuid4().hex[:16]}"
        seed = base.pop("random_seed", None) or random.SystemRandom().randint(1, 2**31 - 1)
        selection = base.pop("selection", "rag")
        stored_config = base | {
            "selection": selection,
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


async def create_error_book_session(
    user_id: str,
    *,
    course_id: str | None = None,
    version_id: str | None = None,
    behavior: str = "immediate",
    order_mode: str = "sequential",
    random_seed: int | None = None,
    idempotency_key: str | None = None,
    max_questions: int = 20,
) -> dict[str, Any]:
    """ApplyHub「错题重练」入口：服务端自查未掌握错题关联题目创建会话。

    The server resolves the question list itself (owner-scoped unmastered
    ErrorItem → published practice-eligible question), so the client never
    assembles question IDs. Ordering: sequential by most recent wrong-attempt
    time descending (stable), or deterministic shuffle via random_seed.
    """
    behavior = str(behavior or "immediate")
    order_mode = str(order_mode or "sequential")
    if behavior not in SUPPORTED_BEHAVIORS:
        raise PracticeError("VALIDATION_FAILED", "不支持的答题行为")
    if order_mode not in SUPPORTED_ORDER_MODES:
        raise PracticeError("VALIDATION_FAILED", "不支持的排序方式")
    limit = max(1, min(int(max_questions or 20), ERROR_BOOK_MAX_QUESTIONS))
    async with get_db_session() as db:
        if idempotency_key:
            prior = (await db.execute(_session_statement_by_key(user_id, idempotency_key))).scalar_one_or_none()
            if prior:
                return _session_payload(prior)
        if not course_id:
            course = (await db.execute(select(Course).where(Course.status == "active").order_by(Course.name))).scalars().first()
            if course is None:
                raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程不可用")
            course_id = course.id
        if not version_id:
            course = await db.get(Course, course_id)
            version_id = (course.default_version_id if course else None) or (await db.execute(
                select(KnowledgeGraphVersion.id).where(KnowledgeGraphVersion.course_id == course_id).order_by(KnowledgeGraphVersion.created_at.desc())
            )).scalar()
        if not version_id:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程尚未发布知识版本")
        version = await db.get(KnowledgeGraphVersion, version_id)
        if version is None or version.course_id != course_id:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程与知识版本不匹配")
        rows = (await db.execute(
            select(ErrorItem.question_id, func.max(ErrorItem.updated_at).label("last_wrong_at"))
            .join(Question, Question.id == ErrorItem.question_id)
            .where(
                ErrorItem.user_id == user_id,
                ErrorItem.is_mastered.is_(False),
                ErrorItem.question_id.isnot(None),
                Question.course_id == course_id, Question.version_id == version_id,
                Question.review_status == "published", Question.practice_eligible.is_(True),
                Question.grading_mode == "deterministic", Question.question_type.in_(SUPPORTED_TYPES),
            )
            .group_by(ErrorItem.question_id)
            .order_by(func.max(ErrorItem.updated_at).desc())
        )).all()
        question_ids = [row.question_id for row in rows if row.question_id]
        if not question_ids:
            raise PracticeError("INSUFFICIENT_QUESTION_POOL", "暂无待重练的错题", {"requested": limit, "available": 0})
        question_ids = question_ids[:limit]
        seed = int(random_seed) if random_seed is not None else random.SystemRandom().randint(1, 2**31 - 1)
        if order_mode == "random":
            random.Random(seed).shuffle(question_ids)
    config: dict[str, Any] = {
        "selection": "error_book", "source": "error_book",
        "behavior": behavior, "order_mode": order_mode, "random_seed": seed,
    }
    if idempotency_key:
        config["idempotency_key"] = idempotency_key
    return await create_session_from_questions(user_id, question_ids, course_id, version_id, config)


async def save_practice_snapshot(user_id: str, session_id: str, current_question_id: str | None) -> dict[str, Any]:
    """Persist the resumable UI position for practice sessions (mirrors exam)."""
    async with get_db_session() as db:
        session = (await db.execute(_session_statement(session_id, user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
        if session.status == "completed":
            return {"completed": True, "completion_reason": session.completion_reason}
        if session.status != "in_progress":
            raise PracticeError("SESSION_STATE_CONFLICT", "会话尚未开始")
        if current_question_id and not any(row.question_id == current_question_id for row in session.questions):
            raise PracticeError("VALIDATION_FAILED", "题目不属于该练习会话")
        now = datetime.now(timezone.utc)
        session.recovery_snapshot = {"current_question_id": current_question_id}
        session.recovery_snapshot_at = now
        await db.flush()
        return {"completed": False, "current_question_id": current_question_id, "saved_at": now}


def _balanced_select(questions: list[Question], codes: dict[str, list[str]], count: int, seed: int, order_mode: str = "random") -> list[Question]:
    if order_mode == "sequential":
        # 顺序模式：按题号稳定排序后直接截取，可复现且不依赖随机种子。
        return sorted(questions, key=lambda q: q.id)[:count]
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


def _attempt_kind_of(session_context: dict[str, Any]) -> str:
    return {
        "original_correct": "original_retry", "variant_correct": "variant",
        "spaced_correct": "spaced_review",
    }.get(session_context.get("review_kind"), "regular")


def _compose_signals(session_context: dict[str, Any], learning_signals: dict[str, Any] | None, behavior: str, submission_index: int) -> dict[str, Any]:
    """Merge client signals with server context; adaptive decay only weights mastery, never the grade."""
    signals = dict(learning_signals or {})
    signals["attempt_kind"] = _attempt_kind_of(session_context)
    if session_context.get("review_interval_days") is not None:
        signals["review_interval_days"] = session_context["review_interval_days"]
    if behavior == "adaptive":
        signals["mastery_weight"] = ADAPTIVE_MASTERY_WEIGHTS[min(submission_index, len(ADAPTIVE_MASTERY_WEIGHTS) - 1)]
    return signals


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _retry_attempt(db, session: PracticeSession, row: PracticeSessionQuestion, attempt: PracticeAttempt, answer: Any, key: str, learning_signals: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Behavior-driven retry: reuse the single attempt row and keep both grades.

    The per-question attempt row (uq_practice_attempt_session_question) is
    updated in place: submissions history preserves every graded answer while
    ``correct``/``user_answer``/``idempotency_key`` reflect the latest one.
    Returns (grading snapshot, outbox ids) — dispatch happens after commit.
    """
    context = session.config_snapshot or {}
    behavior = str(context.get("behavior") or "immediate")
    history = list((attempt.grading_snapshot or {}).get("submissions") or [])
    limit = BEHAVIOR_MAX_SUBMISSIONS.get(behavior, 1)
    if behavior == "deferred" or attempt.correct or len(history) >= limit:
        raise PracticeError("ANSWER_ALREADY_COMMITTED", "该题已提交")
    graded = _grade_one(row.snapshot or {}, answer)
    from app.observability import GRADING_RESULTS
    outcome = "needs_review" if graded.get("needs_review") else ("correct" if graded.get("correct") else "incorrect")
    GRADING_RESULTS.labels(outcome).inc()
    classification = classify_error(row.snapshot or {}, answer, correct=graded["correct"])
    history.append({"answer": answer, "correct": bool(graded["correct"]), "submitted_at": _now_iso()})
    signals = _compose_signals(context, learning_signals, behavior, len(history) - 1)
    signals["retry"] = True
    graded_extra = {k: v for k, v in graded.items() if k not in {"correct", "correct_answer", "needs_review"}}
    result = {**(attempt.grading_snapshot or {}), "question_id": row.question_id, "correct": bool(graded["correct"]), "needs_review": bool(graded.get("needs_review")), "correct_answer": graded["correct_answer"], "analysis": (row.snapshot or {}).get("analysis") or "", "error_category": classification["category"] if classification else None, "error_classification": classification, "learning_signals": signals, **graded_extra, "submissions": history, "retry_count": len(history) - 1}
    attempt.user_answer = answer
    attempt.correct = bool(graded["correct"])
    attempt.idempotency_key = key
    attempt.grading_snapshot = result
    await db.flush()
    db.add(LearningRecord(
        user_id=session.user_id, question_id=row.question_id, event_type="practice_answer",
        question_content=(row.snapshot or {}).get("content") or "",
        category=((row.snapshot or {}).get("knowledge_point_codes") or ["高等数学"])[0],
        difficulty=(row.snapshot or {}).get("difficulty") or 3,
        user_answer=json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str) else answer,
        correct_answer=str(graded["correct_answer"]), is_correct=bool(graded["correct"]),
        metadata_={"session_id": session.id, "attempt_id": attempt.id, "learning_signals": signals, "retry": True, "mode": "practice", "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or []},
    ))
    category = ((row.snapshot or {}).get("knowledge_point_codes") or [""])[0]
    await db.flush()
    from app.services.learning_projection import rebuild_learning_projections_in_session
    await rebuild_learning_projections_in_session(db, session.user_id)
    from app.services.outbox import enqueue_outbox
    outbox_ids: list[str] = []
    refresh = await enqueue_outbox(
        db, event_type="learning.refresh", aggregate_type="practice_attempt",
        aggregate_id=attempt.id, user_id=session.user_id, payload={"category": category},
        idempotency_key=f"learning-refresh:attempt:{attempt.id}:retry-{len(history)}",
    )
    outbox_ids.append(refresh.id)
    if graded["correct"] and context.get("review_schedule_id"):
        review = await enqueue_outbox(
            db, event_type="review.complete", aggregate_type="practice_attempt",
            aggregate_id=attempt.id, user_id=session.user_id,
            payload={"review_schedule_id": int(context["review_schedule_id"]), "attempt_id": attempt.id},
            idempotency_key=f"auto-review:{attempt.id}:retry-{len(history)}",
        )
        outbox_ids.append(review.id)
    return result, outbox_ids


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
        session_context = session.config_snapshot or {}
        behavior = str(session_context.get("behavior") or "immediate")
        attempt = next((a for a in session.attempts if a.session_question_id == row.id), None)
        if attempt:
            if attempt.idempotency_key != key:
                retry_result, retry_outbox_ids = await _retry_attempt(db, session, row, attempt, answer, key, learning_signals)
                from app.services.outbox import dispatch_outbox_best_effort
                for event_id in retry_outbox_ids:
                    dispatch_outbox_best_effort(event_id)
                return retry_result
            if behavior == "deferred":
                # Idempotent replay under deferred must not leak the grade either.
                return {"question_id": question_id, "submitted": True, "feedback_deferred": True}
            return attempt.grading_snapshot
        graded = _grade_one(row.snapshot or {}, answer)
        from app.observability import GRADING_RESULTS
        outcome = "needs_review" if graded.get("needs_review") else ("correct" if graded.get("correct") else "incorrect")
        GRADING_RESULTS.labels(outcome).inc()
        classification = classify_error(row.snapshot or {}, answer, correct=graded["correct"])
        signals = _compose_signals(session_context, learning_signals, behavior, 0)
        # 判分扩展键（multi_choice 的 partial_credit/scoring 等）原样透出，报告端按需消费
        graded_extra = {k: v for k, v in graded.items() if k not in {"correct", "correct_answer", "needs_review"}}
        result = {"question_id": question_id, "question_content": (row.snapshot or {}).get("content") or "", "correct": graded["correct"], "needs_review": bool(graded.get("needs_review")), "correct_answer": graded["correct_answer"], "analysis": (row.snapshot or {}).get("analysis") or "", "difficulty": (row.snapshot or {}).get("difficulty") or 3, "estimated_time": (row.snapshot or {}).get("estimated_time"), "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or [], "error_category": classification["category"] if classification else None, "error_classification": classification, "learning_signals": signals, **graded_extra, "submissions": [{"answer": answer, "correct": bool(graded["correct"]), "submitted_at": _now_iso()}], "retry_count": 0}
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
    if behavior == "deferred":
        # 学习事实（判分/错题回流/投影）照常落库，只是完成前不向学生反馈。
        return {"question_id": question_id, "submitted": True, "feedback_deferred": True}
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
            item = {"question_id": row.question_id, "question_content": (row.snapshot or {}).get("content") or "", "correct": False, "your_answer": "（未作答）", "correct_answer": (row.snapshot or {}).get("answer_spec", {}).get("correct"), "analysis": (row.snapshot or {}).get("analysis") or "", "knowledge_point_codes": (row.snapshot or {}).get("knowledge_point_codes") or [], "error_category": classification["category"], "error_classification": classification}
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
    # Listing recent timed sessions is also a server-authoritative deadline check.
    async with get_db_session() as db:
        active_rows = list((await db.execute(select(PracticeSession.id, PracticeSession.mode).where(
            PracticeSession.user_id == user_id,
            PracticeSession.mode.in_(("exam", "assessment")),
            PracticeSession.status == "in_progress",
        ).limit(limit))).all())
    if active_rows:
        from app.services.assessment_service import get_assessment
        from app.services.exam_service import get_exam
        for session_id, mode in active_rows:
            checker = get_assessment if mode == "assessment" else get_exam
            await checker(user_id, session_id)
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
