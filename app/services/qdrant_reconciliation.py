"""SQL-authoritative Qdrant reconciliation and explicitly gated rebuilds."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import select

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Memory, Question
from app.services.vector_store import get_vector_store
from app.services.memory_vector_store import get_memory_vector_store


@dataclass
class ReconciliationReport:
    kind: str
    collection: str
    expected: int = 0
    actual: int = 0
    missing: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    wrong_collection: list[str] = field(default_factory=list)
    user_scope_errors: list[str] = field(default_factory=list)
    embedding_version_mismatch: list[str] = field(default_factory=list)

    @property
    def different(self) -> int:
        return sum(map(len, (self.missing, self.stale, self.wrong_collection, self.user_scope_errors, self.embedding_version_mismatch)))

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "collection": self.collection, "expected": self.expected, "actual": self.actual,
                "missing": self.missing, "stale": self.stale, "wrong_collection": self.wrong_collection,
                "user_scope_errors": self.user_scope_errors, "embedding_version_mismatch": self.embedding_version_mismatch,
                "different": self.different}


def _expected_version(kind: str) -> str:
    return settings.MEMORY_EMBEDDING_MODEL if kind == "memory" else settings.VECTOR_EMBEDDING_MODEL


def _point_key(kind: str, payload: dict[str, Any], point_id: Any) -> str:
    key = payload.get("memory_id" if kind == "memory" else "question_id")
    return str(key if key is not None else point_id)


async def _scroll(client: Any, collection: str) -> list[Any]:
    points: list[Any] = []
    offset = None
    while True:
        batch, offset = await asyncio.to_thread(client.scroll, collection_name=collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        points.extend(batch)
        if offset is None:
            return points


async def reconcile(kind: str, *, user_id: str | None = None, client: Any = None) -> ReconciliationReport:
    if kind not in {"question", "memory"}:
        raise ValueError("kind must be question or memory")
    collection = settings.MEMORY_QDRANT_COLLECTION if kind == "memory" else settings.QUESTION_QDRANT_COLLECTION
    if client is None:
        if kind == "memory":
            memory_store = get_memory_vector_store()
            await memory_store.initialize()
            client = memory_store._client
        else:
            client = (await get_vector_store())._client
    async with get_db_session() as db:
        if kind == "memory":
            stmt = select(Memory).where(Memory.status == "active", Memory.deleted_at.is_(None))
            if user_id:
                stmt = stmt.where(Memory.user_id == user_id)
            facts = list((await db.scalars(stmt)).all())
        else:
            facts = list((await db.scalars(select(Question).where(Question.review_status == "published"))).all())
    expected = {str(x.id): x for x in facts}
    try:
        collections = await asyncio.to_thread(client.get_collections)
        names = {str(x.name) for x in collections.collections}
        if collection not in names:
            report = ReconciliationReport(kind=kind, collection=collection, expected=len(expected))
            report.wrong_collection.append(collection)
            return report
    except Exception:
        # The scroll below provides the authoritative transport error.
        pass
    points = await _scroll(client, collection)
    report = ReconciliationReport(kind=kind, collection=collection, expected=len(expected), actual=len(points))
    seen: set[str] = set()
    version = _expected_version(kind)
    for point in points:
        payload = point.payload or {}
        key = _point_key(kind, payload, point.id)
        if key not in expected:
            report.stale.append(key)
            continue
        seen.add(key)
        if kind == "memory" and str(payload.get("user_id")) != str(expected[key].user_id):
            report.user_scope_errors.append(key)
        if kind == "question" and payload.get("user_id") is not None:
            report.user_scope_errors.append(key)
        if payload.get("embedding_version") != version and payload.get("embedding_model") != version:
            report.embedding_version_mismatch.append(key)
    report.missing = sorted(set(expected) - seen)
    return report


async def rebuild(kind: str, *, user_id: str | None = None, execute: bool = False, rate_limit: float = 0.0, retries: int = 3) -> dict[str, Any]:
    if not execute:
        return {"dry_run": True, "report": (await reconcile(kind, user_id=user_id)).as_dict()}
    if kind not in {"question", "memory"}:
        raise ValueError("kind must be question or memory")
    if kind == "memory" and not user_id:
        raise PermissionError("memory rebuild requires --user-id")
    async with get_db_session() as db:
        if kind == "memory":
            facts = list((await db.scalars(select(Memory).where(Memory.user_id == user_id, Memory.status == "active", Memory.deleted_at.is_(None)))).all())
        else:
            facts = list((await db.scalars(select(Question).where(Question.review_status == "published"))).all())
    done = 0; failed: list[str] = []
    for fact in facts:
        for attempt in range(max(1, retries)):
            try:
                if kind == "memory":
                    await get_memory_vector_store().upsert(fact)
                else:
                    text = fact.content + ("\n" + fact.analysis if fact.analysis else "")
                    await (await get_vector_store()).add_question(str(fact.id), text, {"content": fact.content, "content_kind": "question", "review_status": fact.review_status, "embedding_model": settings.VECTOR_EMBEDDING_MODEL, "embedding_version": settings.VECTOR_EMBEDDING_MODEL})
                done += 1
                break
            except Exception:
                if attempt + 1 == max(1, retries): failed.append(str(fact.id))
                else: await asyncio.sleep(min(30, 2 ** attempt))
        if rate_limit > 0: await asyncio.sleep(rate_limit)
    return {"dry_run": False, "requested": len(facts), "rebuilt": done, "failed": failed}
