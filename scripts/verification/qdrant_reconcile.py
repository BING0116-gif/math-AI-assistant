"""Qdrant reconciliation/rebuild CLI. Rebuild is dry-run unless --execute is supplied."""
import argparse, asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.services.qdrant_reconciliation import reconcile, rebuild
from app.data.database import close_db, init_db

async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["question", "memory"], required=True)
    p.add_argument("--user-id")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--rate-limit", type=float, default=0.0)
    p.add_argument("--retries", type=int, default=3)
    a = p.parse_args()
    if a.execute and a.kind == "memory" and not a.user_id:
        p.error("--execute memory rebuild requires --user-id")
    await init_db()
    try:
        result = await rebuild(a.kind, user_id=a.user_id, execute=a.execute, rate_limit=a.rate_limit, retries=a.retries)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result.get("failed") else 1
    finally:
        await close_db()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
