"""Owner-scoped reusable student papers and session launching."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    KnowledgeGraphVersion,
    KnowledgePoint,
    PracticeSession,
    PracticeSessionQuestion,
    Question,
    QuestionKnowledgePoint,
    StudentPaper,
    StudentPaperQuestion,
)
from app.services.practice_service import PracticeError, _question_snapshot


def _paper_stmt(user_id: str, paper_id: str):
    return select(StudentPaper).where(
        StudentPaper.id == paper_id,
        StudentPaper.user_id == user_id,
    ).options(selectinload(StudentPaper.questions))


def _paper_payload(paper: StudentPaper, *, include_questions: bool = True) -> dict[str, Any]:
    payload = {
        "paper_id": paper.id,
        "title": paper.title,
        "course_id": paper.course_id,
        "version_id": paper.version_id,
        "source_type": paper.source_type,
        "status": paper.status,
        "blueprint_snapshot": paper.blueprint_snapshot or {},
        "revision": paper.revision,
        "question_count": len(paper.questions),
        "total_score": sum(float(row.score or 0) for row in paper.questions),
        "estimated_minutes": max(1, sum(int((row.question_snapshot or {}).get("estimated_time") or 2) for row in paper.questions)),
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }
    if include_questions:
        payload["questions"] = [
            {
                "item_id": row.id,
                "question_id": row.question_id,
                "position": row.position,
                "score": row.score,
                "selection_reason": row.selection_reason,
                **{key: (row.question_snapshot or {}).get(key) for key in (
                    "content", "question_type", "options", "difficulty",
                    "estimated_time", "knowledge_point_codes",
                )},
            }
            for row in paper.questions
        ]
    return payload


async def _load_question_snapshots(db, *, course_id: str, version_id: str, question_ids: list[str]) -> list[tuple[Question, list[str]]]:
    if not question_ids:
        return []
    rows = (await db.execute(
        select(Question, KnowledgePoint.code)
        .join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id)
        .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
        .where(
            Question.id.in_(question_ids),
            Question.course_id == course_id,
            Question.version_id == version_id,
            Question.review_status == "published",
            Question.auto_grading_eligible.is_(True),
        )
    )).all()
    grouped: dict[str, tuple[Question, list[str]]] = {}
    for question, code in rows:
        grouped.setdefault(question.id, (question, []))[1].append(code)
    missing = [qid for qid in question_ids if qid not in grouped]
    if missing:
        raise PracticeError("QUESTION_NOT_AVAILABLE", "部分题目不可用于学生试卷", {"question_ids": missing})
    return [grouped[qid] for qid in question_ids]


async def _select_from_buckets(db, *, course_id: str, version_id: str, buckets: list[dict[str, Any]], seed: int) -> tuple[list[str], list[dict[str, Any]]]:
    rng = random.Random(seed)
    selected: list[str] = []
    reasons: list[dict[str, Any]] = []
    for bucket in buckets:
        code = str(bucket.get("knowledge_point_code") or "")
        count = max(0, min(int(bucket.get("count") or 0), 30))
        if not code or not count:
            continue
        stmt = (
            select(Question.id)
            .join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .where(
                Question.course_id == course_id,
                Question.version_id == version_id,
                Question.review_status == "published",
                Question.exam_eligible.is_(True),
                Question.auto_grading_eligible.is_(True),
                KnowledgePoint.code == code,
            )
        )
        if bucket.get("difficulty_min") is not None:
            stmt = stmt.where(Question.difficulty >= int(bucket["difficulty_min"]))
        if bucket.get("difficulty_max") is not None:
            stmt = stmt.where(Question.difficulty <= int(bucket["difficulty_max"]))
        candidates = [value for value in (await db.execute(stmt)).scalars().all() if value not in selected]
        rng.shuffle(candidates)
        if len(candidates) < count:
            raise PracticeError("INSUFFICIENT_QUESTION_POOL", "蓝图对应的正式题目不足", {"knowledge_point_code": code, "requested": count, "available": len(candidates)})
        for question_id in candidates[:count]:
            selected.append(question_id)
            reasons.append({"quota_kind": bucket.get("quota_kind"), "knowledge_point_code": code, "reason": bucket.get("reason")})
    return selected, reasons


async def list_papers(user_id: str, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    async with get_db_session() as db:
        rows = list((await db.execute(
            select(StudentPaper)
            .where(StudentPaper.user_id == user_id, StudentPaper.status != "archived")
            .options(selectinload(StudentPaper.questions))
            .order_by(StudentPaper.updated_at.desc())
            .offset(offset).limit(limit)
        )).scalars())
        return {"items": [_paper_payload(row, include_questions=False) for row in rows], "limit": limit, "offset": offset}


async def create_paper(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_db_session() as db:
        version = await db.get(KnowledgeGraphVersion, payload["version_id"])
        if not version or version.status != "published" or version.course_id != payload["course_id"]:
            raise PracticeError("COURSE_VERSION_NOT_AVAILABLE", "课程与发布版本不匹配")
        question_ids = list(dict.fromkeys(payload.get("question_ids") or []))
        reasons: list[dict[str, Any] | None] = [None] * len(question_ids)
        buckets = payload.get("blueprint_buckets") or []
        seed = int(payload.get("random_seed") or random.SystemRandom().randint(1, 2**31 - 1))
        if not question_ids and buckets:
            question_ids, reasons = await _select_from_buckets(db, course_id=version.course_id, version_id=version.id, buckets=buckets, seed=seed)
        snapshots = await _load_question_snapshots(db, course_id=version.course_id, version_id=version.id, question_ids=question_ids)
        paper = StudentPaper(
            user_id=user_id,
            title=(payload.get("title") or "未命名试卷").strip()[:200],
            course_id=version.course_id,
            version_id=version.id,
            source_type=payload.get("source_type") or "manual",
            status="draft",
            blueprint_snapshot={"buckets": buckets, "random_seed": seed, **(payload.get("blueprint_snapshot") or {})},
        )
        db.add(paper); await db.flush()
        for index, (question, codes) in enumerate(snapshots):
            db.add(StudentPaperQuestion(
                paper_id=paper.id,
                question_id=question.id,
                position=index + 1,
                score=float(payload.get("default_score") or 1),
                question_snapshot=_question_snapshot(question, sorted(set(codes))),
                selection_reason=reasons[index] if index < len(reasons) else None,
            ))
        await db.flush()
        loaded = (await db.execute(_paper_stmt(user_id, paper.id))).scalar_one()
        return _paper_payload(loaded)


async def get_paper(user_id: str, paper_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id))).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        return _paper_payload(paper)


async def update_paper(user_id: str, paper_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        if paper.revision != payload["expected_revision"]:
            raise PracticeError("REVISION_CONFLICT", "试卷已在其他位置更新", {"current_revision": paper.revision})
        if payload.get("title") is not None:
            paper.title = payload["title"].strip()[:200]
        if payload.get("status") is not None:
            paper.status = payload["status"]
        paper.revision += 1
        await db.flush()
        return _paper_payload(paper)


async def add_question(user_id: str, paper_id: str, question_id: str, score: float = 1.0) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        if paper.status == "archived":
            raise PracticeError("PAPER_STATE_CONFLICT", "归档试卷不可编辑")
        snapshots = await _load_question_snapshots(db, course_id=paper.course_id, version_id=paper.version_id, question_ids=[question_id])
        if any(row.question_id == question_id for row in paper.questions):
            raise PracticeError("QUESTION_ALREADY_EXISTS", "题目已在试卷中")
        question, codes = snapshots[0]
        db.add(StudentPaperQuestion(paper_id=paper.id, question_id=question.id, position=len(paper.questions) + 1, score=score, question_snapshot=_question_snapshot(question, codes)))
        paper.status = "draft"; paper.revision += 1
        await db.flush()
        loaded = (await db.execute(_paper_stmt(user_id, paper_id))).scalar_one()
        return _paper_payload(loaded)


async def replace_question(user_id: str, paper_id: str, item_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        item = next((row for row in paper.questions if row.id == item_id), None)
        if not item:
            raise PracticeError("QUESTION_NOT_FOUND", "试卷题目不存在")
        snap = item.question_snapshot or {}
        codes = snap.get("knowledge_point_codes") or []
        existing = [row.question_id for row in paper.questions]
        stmt = select(Question.id).where(
            Question.course_id == paper.course_id,
            Question.version_id == paper.version_id,
            Question.review_status == "published",
            Question.exam_eligible.is_(True),
            Question.auto_grading_eligible.is_(True),
            Question.question_type == snap.get("question_type"),
            Question.difficulty.between(max(1, int(snap.get("difficulty") or 3) - 1), min(5, int(snap.get("difficulty") or 3) + 1)),
            Question.id.not_in(existing),
        )
        if codes:
            stmt = stmt.join(QuestionKnowledgePoint, QuestionKnowledgePoint.question_id == Question.id).join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id).where(KnowledgePoint.code.in_(codes))
        replacement_id = (await db.execute(stmt.order_by(Question.usage_count.asc(), Question.id.asc()).limit(1))).scalar_one_or_none()
        if not replacement_id:
            raise PracticeError("INSUFFICIENT_QUESTION_POOL", "没有可替换的同类正式题目")
        question, replacement_codes = (await _load_question_snapshots(db, course_id=paper.course_id, version_id=paper.version_id, question_ids=[replacement_id]))[0]
        item.question_id = replacement_id
        item.question_snapshot = _question_snapshot(question, replacement_codes)
        item.selection_reason = {"action": "replacement", "replaced_question_id": snap.get("question_id")}
        paper.status = "draft"; paper.revision += 1
        await db.flush()
        return _paper_payload(paper)


async def remove_question(user_id: str, paper_id: str, item_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        item = next((row for row in paper.questions if row.id == item_id), None)
        if not item:
            raise PracticeError("QUESTION_NOT_FOUND", "试卷题目不存在")
        await db.delete(item); await db.flush()
        remaining = [row for row in paper.questions if row.id != item_id]
        for index, row in enumerate(remaining, 1):
            row.position = -index
        await db.flush()
        for index, row in enumerate(remaining, 1):
            row.position = index
        paper.status = "draft"; paper.revision += 1
        await db.flush()
        return _paper_payload(paper)


async def reorder_questions(user_id: str, paper_id: str, item_ids: list[str], expected_revision: int) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        if paper.revision != expected_revision:
            raise PracticeError("REVISION_CONFLICT", "试卷已在其他位置更新", {"current_revision": paper.revision})
        by_id = {row.id: row for row in paper.questions}
        if len(item_ids) != len(by_id) or set(item_ids) != set(by_id):
            raise PracticeError("VALIDATION_FAILED", "题目顺序必须完整且不能重复")
        for index, item_id in enumerate(item_ids, 1): by_id[item_id].position = -index
        await db.flush()
        for index, item_id in enumerate(item_ids, 1): by_id[item_id].position = index
        paper.status = "draft"; paper.revision += 1
        await db.flush()
        return _paper_payload(paper)


async def finalize_paper(user_id: str, paper_id: str, expected_revision: int) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id).with_for_update())).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        if paper.revision != expected_revision:
            raise PracticeError("REVISION_CONFLICT", "试卷已在其他位置更新", {"current_revision": paper.revision})
        if not paper.questions:
            raise PracticeError("VALIDATION_FAILED", "试卷至少需要一道题")
        current_ids = set((await db.execute(select(Question.id).where(
            Question.id.in_([row.question_id for row in paper.questions]),
            Question.review_status == "published",
            Question.exam_eligible.is_(True),
            Question.auto_grading_eligible.is_(True),
        ))).scalars())
        invalid = [row.question_id for row in paper.questions if row.question_id not in current_ids]
        if invalid:
            raise PracticeError("QUESTION_NOT_AVAILABLE", "试卷包含已失效题目，请先替换", {"question_ids": invalid})
        paper.status = "ready"; paper.revision += 1
        await db.flush()
        return _paper_payload(paper)


async def launch_paper(user_id: str, paper_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_db_session() as db:
        paper = (await db.execute(_paper_stmt(user_id, paper_id))).scalar_one_or_none()
        if not paper:
            raise PracticeError("PAPER_NOT_FOUND", "试卷不存在")
        if paper.status != "ready":
            raise PracticeError("PAPER_STATE_CONFLICT", "请先完成并保存试卷")
        mode = payload["mode"]
        key = payload["idempotency_key"]
        prior = (await db.execute(select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.idempotency_key == key))).scalar_one_or_none()
        if prior:
            if prior.source_paper_id != paper.id or prior.mode != ("exam" if mode == "test" else "practice"):
                raise PracticeError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他会话")
            return {"session_id": prior.id, "mode": prior.mode, "status": prior.status}
        if mode == "test" and not payload.get("duration_minutes"):
            raise PracticeError("VALIDATION_FAILED", "测试模式必须设置时长")
        config = {
            "selection_source": "student_paper",
            "source_paper_id": paper.id,
            "paper_title": paper.title,
            "behavior": "deferred" if mode == "test" else payload.get("behavior", "adaptive"),
            "review_policy": "after_submit" if mode == "test" else "during_practice",
            "shuffle_options": False,
        }
        session = PracticeSession(
            user_id=user_id,
            mode="exam" if mode == "test" else "practice",
            source_paper_id=paper.id,
            course_id=paper.course_id,
            version_id=paper.version_id,
            status="created",
            config_snapshot=config,
            random_seed=random.SystemRandom().randint(1, 2**31 - 1),
            idempotency_key=key,
            duration_limit_seconds=int(payload["duration_minutes"] * 60) if mode == "test" else None,
        )
        db.add(session); await db.flush()
        for row in paper.questions:
            db.add(PracticeSessionQuestion(session_id=session.id, question_id=row.question_id, position=row.position, score=row.score, snapshot=dict(row.question_snapshot or {})))
        await db.flush()
        return {"session_id": session.id, "mode": session.mode, "status": session.status, "source_paper_id": paper.id}
