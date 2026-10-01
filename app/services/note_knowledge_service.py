"""Controlled materialization of note AI classifications.

Only this service writes note_knowledge_links; AI output is always treated as
untrusted input and cannot replace a human decision.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from app.data.database import get_db_session
from app.data.models import KnowledgePoint, NoteAiRun, NoteKnowledgeLink, StudyNote
from app.services.note_service import NoteServiceError

HIGH_CONFIDENCE = 0.90
MEDIUM_CONFIDENCE = 0.60


def _data(row: NoteKnowledgeLink, point: KnowledgePoint | None = None):
    return {"link_id": row.id, "note_id": row.note_id, "knowledge_point_id": row.knowledge_point_id,
            "knowledge_point_code": row.knowledge_point_code_snapshot, "knowledge_point_name": point.name if point else None,
            "relation_type": row.relation_type, "source": row.source, "confidence": row.confidence,
            "status": row.status, "ai_run_id": row.ai_run_id, "confirmed_by_user_at": row.confirmed_by_user_at}


async def materialize_ai_suggestions(user_id: str, note_id: str, run_id: str, candidates: list[dict]):
    """Persist only medium/high candidates; low confidence is deliberately absent."""
    async with get_db_session() as db:
        run = await db.scalar(select(NoteAiRun).where(NoteAiRun.id == run_id, NoteAiRun.note_id == note_id, NoteAiRun.user_id == user_id))
        if not run:
            raise NoteServiceError("NOTE_NOT_FOUND", "AI 任务不存在")
        for candidate in candidates:
            confidence = float(candidate["confidence"])
            if confidence < MEDIUM_CONFIDENCE:
                continue
            point = await db.scalar(select(KnowledgePoint).where(KnowledgePoint.code == candidate["knowledge_point_code"], KnowledgePoint.status == "active"))
            if not point:
                continue
            existing = await db.scalar(select(NoteKnowledgeLink).where(NoteKnowledgeLink.note_id == note_id, NoteKnowledgeLink.knowledge_point_id == point.id, NoteKnowledgeLink.relation_type == "covers"))
            # A human decision is final and is never overwritten by a later run.
            if existing and existing.source == "manual":
                continue
            if existing:
                existing.confidence = confidence
                existing.ai_run_id = run_id
                if existing.status != "rejected":
                    existing.status = "confirmed" if confidence >= HIGH_CONFIDENCE else "suggested"
                continue
            db.add(NoteKnowledgeLink(note_id=note_id, user_id=user_id, knowledge_point_id=point.id,
                knowledge_point_code_snapshot=point.code, relation_type="covers", source="ai", confidence=confidence,
                status="confirmed" if confidence >= HIGH_CONFIDENCE else "suggested", ai_run_id=run_id))


async def list_links(user_id: str, note_id: str, status: str | None = None):
    async with get_db_session() as db:
        query = select(NoteKnowledgeLink, KnowledgePoint).join(KnowledgePoint, KnowledgePoint.id == NoteKnowledgeLink.knowledge_point_id).join(StudyNote, StudyNote.id == NoteKnowledgeLink.note_id).where(NoteKnowledgeLink.user_id == user_id, NoteKnowledgeLink.note_id == note_id, StudyNote.status == "active")
        if status:
            query = query.where(NoteKnowledgeLink.status == status)
        rows = (await db.execute(query.order_by(NoteKnowledgeLink.created_at.desc()))).all()
        return [_data(link, point) for link, point in rows]


async def confirm_link(user_id: str, note_id: str, link_id: str, knowledge_point_id: str | None = None):
    async with get_db_session() as db:
        row = await db.scalar(select(NoteKnowledgeLink).where(NoteKnowledgeLink.id == link_id, NoteKnowledgeLink.note_id == note_id, NoteKnowledgeLink.user_id == user_id))
        if not row:
            raise NoteServiceError("NOTE_NOT_FOUND", "知识关联不存在")
        if knowledge_point_id and knowledge_point_id != row.knowledge_point_id:
            point = await db.scalar(select(KnowledgePoint).where(KnowledgePoint.id == knowledge_point_id, KnowledgePoint.status == "active"))
            if not point:
                raise NoteServiceError("NOTE_CONTEXT_INVALID", "知识点不存在或不可用")
            collision = await db.scalar(select(NoteKnowledgeLink).where(NoteKnowledgeLink.note_id == note_id, NoteKnowledgeLink.knowledge_point_id == point.id, NoteKnowledgeLink.relation_type == row.relation_type, NoteKnowledgeLink.id != row.id))
            if collision and collision.source == "manual":
                raise NoteServiceError("NOTE_LINK_CONFLICT", "该知识点已有人工确认关联")
            if collision:
                await db.delete(collision)
            row.knowledge_point_id, row.knowledge_point_code_snapshot = point.id, point.code
        row.source, row.status, row.confirmed_by_user_at = "manual", "confirmed", datetime.now(timezone.utc)
        await db.flush()
        point = await db.get(KnowledgePoint, row.knowledge_point_id)
        return _data(row, point)


async def reject_link(user_id: str, note_id: str, link_id: str):
    async with get_db_session() as db:
        row = await db.scalar(select(NoteKnowledgeLink).where(NoteKnowledgeLink.id == link_id, NoteKnowledgeLink.note_id == note_id, NoteKnowledgeLink.user_id == user_id))
        if not row:
            raise NoteServiceError("NOTE_NOT_FOUND", "知识关联不存在")
        # Rejection is a human outcome and blocks AI rematerialization.
        row.source, row.status, row.confirmed_by_user_at = "manual", "rejected", datetime.now(timezone.utc)
        await db.flush()
        return _data(row, await db.get(KnowledgePoint, row.knowledge_point_id))
