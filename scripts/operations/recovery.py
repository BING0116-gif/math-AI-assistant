"""Auditable repair entrypoint. Read-only unless --apply is explicitly supplied."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.config.settings import settings
from app.data.database import close_db, get_db_session, init_db
from app.data.models import OutboxEvent, Question


def report(operation: str, apply: bool, details: dict) -> None:
    print(json.dumps({"execution_id": str(uuid.uuid4()), "operation": operation,
        "mode": "apply" if apply else "dry-run", "at": datetime.now(timezone.utc).isoformat(),
        "details": details}, ensure_ascii=False, indent=2, default=str))


async def qdrant_sync(apply: bool, question_id: str | None) -> None:
    async with get_db_session() as db:
        query = select(Question).where(Question.review_status == "published")
        if question_id: query = query.where(Question.id == question_id)
        rows = list((await db.execute(query)).scalars().all())
    from app.services.vector_store import get_vector_store
    store = await get_vector_store()
    indexed = set(await store.get_all_ids()) if await store.check_availability() else set()
    sql_ids = {q.id for q in rows}
    missing, stale = sorted(sql_ids - indexed), sorted(indexed - sql_ids) if not question_id else []
    changed = 0
    if apply:
        targets = [q for q in rows if q.id in missing]
        changed = await store.add_questions_batch([(q.id, q.content, {
            "question_type": q.question_type, "difficulty": q.difficulty,
            "review_status": q.review_status}, None) for q in targets])
        for qid in stale:
            changed += int(await store.remove_question(qid))
    report("qdrant_sync", apply, {"sql_published": len(sql_ids), "indexed": len(indexed),
        "missing": missing, "stale": stale, "changed": changed})


async def replay(apply: bool, event_id: str | None) -> None:
    async with get_db_session() as db:
        query = select(OutboxEvent).where(OutboxEvent.status == "dead")
        if event_id:
            query = query.where(OutboxEvent.id == event_id)
        rows = list((await db.execute(query)).scalars())
        ids = [row.id for row in rows]
        if apply:
            for row in rows:
                row.status = "pending"
                row.attempts = 0
                row.available_at = datetime.now(timezone.utc)
                row.locked_at = None
                row.last_error = None
    results = {event_id: "pending" for event_id in ids} if apply else {}
    if apply:
        from app.services.outbox import process_outbox_batch
        results["batch"] = await process_outbox_batch()
    report("replay_outbox", apply, {"event_ids": ids, "results": results})


async def redis_recover(apply: bool, user_id: str | None) -> None:
    import redis.asyncio as redis
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    prefixes = ["profile:", "memory:profile:", "recommendation:", "rate_limit:"]
    keys = []
    for prefix in prefixes:
        pattern = f"{prefix}{user_id}*" if user_id else f"{prefix}*"
        async for key in client.scan_iter(match=pattern, count=500): keys.append(key)
    if apply and keys: await client.delete(*keys)
    await client.aclose()
    report("redis_recover", apply, {"matched_keys": len(keys), "scope_user_id": user_id})


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["qdrant-sync", "replay", "redis-recover"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--user-id")
    parser.add_argument("--question-id")
    parser.add_argument("--event-id")
    args = parser.parse_args()
    database_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL
    if args.operation in {"qdrant-sync", "replay"} and not database_url.startswith("postgresql"):
        raise SystemExit("qdrant-sync/replay require an explicit PostgreSQL DATABASE_URL")
    await init_db()
    try:
        if args.operation == "qdrant-sync": await qdrant_sync(args.apply, args.question_id)
        elif args.operation == "replay": await replay(args.apply, args.event_id)
        else: await redis_recover(args.apply, args.user_id)
    finally:
        await close_db()


if __name__ == "__main__": asyncio.run(main())
