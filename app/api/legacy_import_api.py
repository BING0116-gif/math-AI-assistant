"""One-time, owner-scoped migration of legacy browser state."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.data.database import get_db_session
from app.data.models import ChatMessage, ChatSession, ErrorItem, LegacyClientImport

router = APIRouter(prefix="/api/migrations", tags=["本地历史迁移"])


class LegacyMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class LegacyChat(BaseModel):
    external_session_id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="本地历史", max_length=200)
    messages: list[LegacyMessage] = Field(default_factory=list, max_length=500)


class LegacyError(BaseModel):
    client_item_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=20000)
    question_type: str = Field(default="text", max_length=20)
    error_reason: str = Field(default="", max_length=5000)
    categories: list[str] = Field(default_factory=list, max_length=20)
    original_answer: str = Field(default="", max_length=10000)
    correct_answer: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=10000)
    added_at: str = Field(default="", max_length=64)


class LegacyImportRequest(BaseModel):
    batch_id: str = Field(min_length=8, max_length=128)
    chats: list[LegacyChat] = Field(default_factory=list, max_length=100)
    errors: list[LegacyError] = Field(default_factory=list, max_length=1000)


def _user(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, detail="未认证")
    return str(user_id)


@router.post("/legacy-client")
async def import_legacy_client(request: Request, body: LegacyImportRequest):
    user_id = _user(request)
    now = datetime.now(timezone.utc)
    async with get_db_session() as db:
        prior = await db.scalar(select(LegacyClientImport).where(
            LegacyClientImport.user_id == user_id, LegacyClientImport.batch_id == body.batch_id,
        ))
        if prior:
            return prior.result
        imported_chats = imported_errors = skipped = 0
        for chat in body.chats:
            exists = await db.scalar(select(ChatSession.id).where(
                ChatSession.user_id == user_id, ChatSession.external_session_id == chat.external_session_id,
            ))
            if exists:
                skipped += 1
                continue
            session = ChatSession(
                user_id=user_id, external_session_id=chat.external_session_id,
                title=chat.title or "本地历史", message_count=len(chat.messages),
                context_snapshot={"source": "legacy_client", "migration_batch_id": body.batch_id},
            )
            db.add(session)
            await db.flush()
            for message in chat.messages:
                db.add(ChatMessage(session_id=session.id, role=message.role, content=message.content, metadata_={"source": "legacy_client"}))
            imported_chats += 1
        for item in body.errors:
            exists = await db.scalar(select(ErrorItem.id).where(
                ErrorItem.user_id == user_id, ErrorItem.item_id == item.client_item_id,
            ))
            if exists:
                skipped += 1
                continue
            db.add(ErrorItem(
                user_id=user_id, item_id=item.client_item_id, question=item.question,
                question_type=item.question_type, error_reason=item.error_reason,
                categories=item.categories, knowledge_point_codes=item.categories,
                original_answer=item.original_answer, correct_answer=item.correct_answer,
                notes=item.notes, added_at=item.added_at, source="legacy_client",
                structure_confidence=0.0, review_state="new", is_mastered=False,
            ))
            imported_errors += 1
        result = {"batch_id": body.batch_id, "status": "completed", "imported_chats": imported_chats, "imported_errors": imported_errors, "skipped_items": skipped}
        db.add(LegacyClientImport(
            user_id=user_id, batch_id=body.batch_id, status="completed",
            imported_chats=imported_chats, imported_errors=imported_errors,
            skipped_items=skipped, result=result, completed_at=now,
        ))
        await db.flush()
        return result
