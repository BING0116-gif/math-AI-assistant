"""Fail unless the configured database uses the expected SQLAlchemy dialect."""

import asyncio
import sys

from app.data import database


async def main(expected: str) -> int:
    await database.init_db()
    try:
        actual = database.engine.dialect.name if database.engine is not None else ""
        if actual != expected:
            print(f"database dialect mismatch: expected={expected}, actual={actual}")
            return 1
        print(f"database dialect verified: {actual}")
        return 0
    finally:
        await database.close_db()


if __name__ == "__main__":
    expected_dialect = sys.argv[1] if len(sys.argv) > 1 else "postgresql"
    raise SystemExit(asyncio.run(main(expected_dialect)))
