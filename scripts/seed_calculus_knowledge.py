"""Seed the Phase 1 knowledge catalog after applying Alembic migrations."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.database import get_db_session, init_db, close_db
from app.services.knowledge_seed import seed_phase_one_calculus


async def main() -> None:
    await init_db()
    try:
        async with get_db_session() as session:
            course = await seed_phase_one_calculus(session)
            print(f"Seeded {course.code}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
