"""Seed the released calculus sample and optionally prepare/publish Phase 5 (version 3.0)."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.database import get_db_session, init_db, close_db
from app.services.knowledge_content import publish_calculus_phase5, seed_calculus_phase5, seed_derivative_phase3


async def main(include_phase5_draft: bool = False, publish_phase5: bool = False) -> None:
    await init_db()
    try:
        async with get_db_session() as session:
            if publish_phase5:
                report = await publish_calculus_phase5(session)
                print(
                    f"Published course version {report['version']} as default "
                    f"({report['point_count']} active points, {len(report['chapters'])} chapters)"
                )
                return
            course = await seed_derivative_phase3(session)
            if include_phase5_draft:
                await seed_calculus_phase5(session)
            print(
                f"Seeded released course {course.code} (default version 2.0)"
                + (" and prepared Phase 5 draft" if include_phase5_draft else "")
            )
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-phase5-draft", action="store_true")
    parser.add_argument("--publish-phase5", action="store_true", help="seed content then release version 3.0 through chapter gates")
    args = parser.parse_args()
    asyncio.run(main(args.include_phase5_draft, args.publish_phase5))
