"""Data-governance checks and repair operations.

All operations are explicit and auditable.  The script never prints field
values; the sensitive scan only reports schema fields that require review.
"""
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

from app.data.database import close_db, get_db_session, init_db
from app.data.models import Base, LearningRecord, User


def emit(operation: str, **details):
    print(json.dumps({"execution_id": str(uuid.uuid4()), "operation": operation,
                      "at": datetime.now(timezone.utc).isoformat(), **details},
                     ensure_ascii=False, default=str, indent=2))


async def sensitive_scan() -> None:
    markers = ("password", "token", "secret", "api_key", "access_key", "phone")
    findings = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            name = column.name.lower()
            if any(marker in name for marker in markers):
                findings.append({"table": table.name, "column": column.name, "action": "review masking and retention policy"})
    emit("sensitive_scan", schema_only=True, findings=findings, finding_count=len(findings))


async def recompute_metrics(user_id: str) -> None:
    if not user_id:
        raise SystemExit("--user-id is required")
    from app.services.learning_projection import rebuild_learning_projections
    result = await rebuild_learning_projections(user_id)
    emit("recompute_learning_metrics", user_id=user_id, source="learning_records", result=result)


async def reconcile(user_id: str) -> None:
    if not user_id:
        raise SystemExit("--user-id is required")
    from app.services.qdrant_reconciliation import reconcile as qdrant_reconcile
    from app.services.cache import get_cache_manager
    reports = {}
    for kind in ("memory", "question"):
        try:
            reports[kind] = (await qdrant_reconcile(kind, user_id=user_id if kind == "memory" else None)).as_dict()
        except Exception as exc:
            reports[kind] = {"error": type(exc).__name__ + ": " + str(exc)[:200]}
    cache = get_cache_manager()
    emit("cache_vector_reconcile", user_id=user_id, cache_l1_entries=sum(user_id in key for key in cache.l1_cache), qdrant=reports)


async def deletion_audit(user_id: str) -> None:
    if not user_id:
        raise SystemExit("--user-id is required")
    from app.services.user_data_deletion import preview_user_deletion
    async with get_db_session() as db:
        preview = await preview_user_deletion(db, user_id)
        remaining_records = await db.scalar(select(LearningRecord.id).where(LearningRecord.user_id == user_id).limit(1))
        user_exists = await db.scalar(select(User.id).where(User.id == user_id))
    emit("user_deletion_audit", user_id=user_id, user_account_retained=bool(user_exists), remaining_learning_record=remaining_records is not None, preview=preview.as_dict())


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["sensitive-scan", "recompute-metrics", "reconcile", "deletion-audit"])
    parser.add_argument("--user-id")
    args = parser.parse_args()
    await init_db()
    try:
        if args.operation == "sensitive-scan": await sensitive_scan()
        elif args.operation == "recompute-metrics": await recompute_metrics(args.user_id)
        elif args.operation == "reconcile": await reconcile(args.user_id)
        else: await deletion_audit(args.user_id)
    finally:
        await close_db()


if __name__ == "__main__": asyncio.run(main())
