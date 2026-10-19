"""Read-only acceptance probe for the real PostgreSQL/Redis/Qdrant stack.

This command never creates users, writes learning facts, changes Qdrant, or
changes rollout flags. It is intentionally separate from SQLite unit gates.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only runtime dependency acceptance")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    from app.config.settings import settings
    from app.data.database import get_db_session
    from sqlalchemy import text

    report: dict[str, object] = {"mutations": [], "checks": {}}
    db_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL
    if not db_url.startswith("postgresql"):
        report["checks"]["postgresql"] = {"status": "blocked", "reason": "ASYNC_DATABASE_URL/DATABASE_URL must be PostgreSQL"}
    else:
        try:
            async with get_db_session() as db:
                await db.execute(text("SELECT 1"))
            report["checks"]["postgresql"] = {"status": "ready", "url_scheme": "postgresql"}
        except Exception as exc:
            report["checks"]["postgresql"] = {"status": "error", "error": str(exc)[:300]}

    try:
        import redis.asyncio as redis
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        report["checks"]["redis"] = {"status": "ready", "url_scheme": settings.REDIS_URL.split(":", 1)[0]}
    except Exception as exc:
        report["checks"]["redis"] = {"status": "error", "error": str(exc)[:300]}

    try:
        from app.services.vector_store import get_vector_store
        store = await get_vector_store()
        available = await store.check_availability()
        stats = await store.get_collection_stats()
        report["checks"]["qdrant"] = {"status": "ready" if available and "error" not in stats else "degraded", "stats": stats}
    except Exception as exc:
        report["checks"]["qdrant"] = {"status": "error", "error": str(exc)[:300]}

    report["status"] = "ready" if all(value.get("status") == "ready" for value in report["checks"].values()) else "blocked_or_degraded"
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report)
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
