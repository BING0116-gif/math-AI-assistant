"""Unified, user-scoped application service for chat and durable memories.

SQL is authoritative. Vector indexes may accelerate retrieval elsewhere, but
must never be the only copy of a student's memory.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select

from app.data.database import get_db_session
from app.data.models import ChatMessage, ChatSession, Memory, MemoryAccessLog


@dataclass(frozen=True)
class RetrievedMemory:
    id: int
    memory_type: str
    content: str
    score: float
    source: str = "sql"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }


class MemoryApplicationService:
    """Owns durable chat history and long-term memory retrieval."""

    _PREFERENCE_PATTERNS = (
        re.compile(r"(?:我喜欢|我偏好|我不喜欢|请以后|以后请|我的目标是|我正在学|我容易)([^。！？\n]{1,160})"),
    )

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_db_session

    async def ensure_session(self, user_id: str, external_session_id: str) -> str:
        self._validate_scope(user_id, external_session_id)
        async with self._session_factory() as db:
            result = await db.execute(select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.external_session_id == external_session_id,
            ))
            row = result.scalar_one_or_none()
            if row is None:
                row = ChatSession(user_id=user_id, external_session_id=external_session_id)
                db.add(row)
                await db.flush()
            await db.commit()
            return row.id

    async def load_recent_messages(
        self, user_id: str, external_session_id: str, limit: int = 20
    ) -> List[Dict[str, str]]:
        self._validate_scope(user_id, external_session_id)
        limit = max(1, min(int(limit), 100))
        async with self._session_factory() as db:
            session = (await db.execute(select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.external_session_id == external_session_id,
            ))).scalar_one_or_none()
            if session is None:
                return []
            rows = list((await db.execute(
                select(ChatMessage).where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit)
            )).scalars())
            rows.reverse()
            return [{"role": row.role, "content": row.content} for row in rows]

    async def list_chat_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not user_id: raise ValueError("user_id is required")
        async with self._session_factory() as db:
            rows = list((await db.execute(select(ChatSession).where(
                ChatSession.user_id == user_id, ChatSession.status != "archived",
            ).order_by(ChatSession.updated_at.desc()).limit(max(1, min(limit, 100))))).scalars())
            return [{"id": row.external_session_id, "title": row.title, "status": row.status, "message_count": row.message_count, "default_tutor_mode": row.default_tutor_mode, "context": row.context_snapshot or {}, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]

    async def get_chat_session(self, user_id: str, external_session_id: str) -> Dict[str, Any] | None:
        self._validate_scope(user_id, external_session_id)
        async with self._session_factory() as db:
            row = (await db.execute(select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.external_session_id == external_session_id))).scalar_one_or_none()
            if row is None or row.status == "archived": return None
            messages = list((await db.execute(select(ChatMessage).where(ChatMessage.session_id == row.id).order_by(ChatMessage.created_at, ChatMessage.id))).scalars())
            return {"id": row.external_session_id, "title": row.title, "status": row.status, "default_tutor_mode": row.default_tutor_mode, "context": row.context_snapshot or {}, "messages": [{"id": item.id, "role": item.role, "content": item.content, "metadata": item.metadata_ or {}, "created_at": item.created_at} for item in messages]}

    async def update_chat_session(self, user_id: str, external_session_id: str, *, title: str | None = None, default_tutor_mode: str | None = None, archive: bool = False) -> Dict[str, Any]:
        self._validate_scope(user_id, external_session_id)
        async with self._session_factory() as db:
            row = (await db.execute(select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.external_session_id == external_session_id))).scalar_one_or_none()
            if row is None: raise LookupError("chat session not found")
            if title is not None: row.title = title[:200]
            if default_tutor_mode is not None: row.default_tutor_mode = default_tutor_mode
            if archive: row.status = "archived"
            row.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return {"id": row.external_session_id, "title": row.title, "status": row.status, "default_tutor_mode": row.default_tutor_mode}

    async def append_message(
        self,
        user_id: str,
        external_session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("unsupported chat role")
        if not content:
            raise ValueError("message content is required")
        internal_id = await self.ensure_session(user_id, external_session_id)
        async with self._session_factory() as db:
            # Re-check ownership in the write transaction.
            owner = (await db.execute(select(ChatSession).where(
                ChatSession.id == internal_id, ChatSession.user_id == user_id
            ))).scalar_one_or_none()
            if owner is None:
                raise PermissionError("chat session does not belong to user")
            message = ChatMessage(
                session_id=internal_id, role=role, content=content,
                metadata_=metadata or {},
            )
            db.add(message)
            owner.message_count = int(owner.message_count or 0) + 1
            if role == "user" and owner.message_count == 1 and owner.title == "新对话":
                owner.title = re.sub(r"\s+", " ", content).strip()[:40] or "新对话"
            owner.updated_at = datetime.now(timezone.utc)
            await db.flush()
            message_id = message.id
            await db.commit()
        if role == "user":
            await self.remember_explicit_preferences(user_id, content, str(message_id))
        return message_id

    async def remember_explicit_preferences(
        self, user_id: str, text: str, source_message_id: str
    ) -> int:
        """Persist only explicit user statements; never infer sensitive traits."""
        candidates: List[str] = []
        for pattern in self._PREFERENCE_PATTERNS:
            for match in pattern.finditer(text or ""):
                value = match.group(0).strip()[:200]
                if value and value not in candidates:
                    candidates.append(value)
        created = 0
        now = int(time.time())
        async with self._session_factory() as db:
            for content in candidates[:3]:
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
                source_id = f"explicit:{digest}"
                exists = (await db.execute(select(Memory.id).where(
                    Memory.user_id == user_id,
                    Memory.memory_type == "preference",
                    Memory.source_id == source_id,
                    Memory.deleted_at.is_(None),
                ))).scalar_one_or_none()
                if exists is not None:
                    continue
                db.add(Memory(
                    user_id=user_id,
                    memory_type="preference",
                    high_category="profile",
                    category="explicit_preference",
                    content=content,
                    embedding_summary=content,
                    importance=0.8,
                    status="active",
                    expire_at=now + 365 * 24 * 3600,
                    memory_strength=0.8,
                    source_id=source_id,
                    created_at=now,
                ))
                created += 1
            await db.commit()
        return created

    async def retrieve(
        self, user_id: str, query: str, session_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        self._validate_scope(user_id, session_id)
        now = int(time.time())
        tokens = self._tokens(query)
        async with self._session_factory() as db:
            rows = list((await db.execute(select(Memory).where(
                Memory.user_id == user_id,
                Memory.status == "active",
                Memory.deleted_at.is_(None),
                or_(Memory.expire_at.is_(None), Memory.expire_at > now),
            ).order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(200))).scalars())
            ranked = []
            for row in rows:
                haystack = f"{row.content} {row.embedding_summary} {row.category}".lower()
                overlap = sum(1 for token in tokens if token in haystack)
                relevance = overlap / max(1, len(tokens))
                if tokens and relevance == 0 and row.memory_type != "preference":
                    continue
                score = 0.55 * relevance + 0.25 * float(row.importance or 0) + 0.2 * float(row.memory_strength or 0)
                ranked.append((score, row))
            ranked.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
            selected = ranked[:max(1, min(int(limit), 10))]
            for _, row in selected:
                row.last_accessed = now
                row.access_count = int(row.access_count or 0) + 1
                db.add(MemoryAccessLog(
                    memory_id=row.id, user_id=user_id,
                    session_id=session_id, accessed_at=now,
                ))
            await db.commit()
            return [RetrievedMemory(
                id=row.id, memory_type=row.memory_type,
                content=row.content[:500], score=round(score, 4),
            ).to_dict() for score, row in selected]

    @staticmethod
    def _tokens(text: str) -> List[str]:
        latin = re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower())
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
        return list(dict.fromkeys(latin + chinese))[:30]

    @staticmethod
    def _validate_scope(user_id: str, session_id: str) -> None:
        if not user_id:
            raise ValueError("user_id is required")
        if not session_id or len(session_id) > 128:
            raise ValueError("valid session_id is required")
