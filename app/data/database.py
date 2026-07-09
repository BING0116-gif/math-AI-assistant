import os
import logging
import time
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
)

from app.config.settings import settings
from app.data.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = settings.DATABASE_URL
ASYNC_DATABASE_URL = settings.ASYNC_DATABASE_URL

engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _get_database_url() -> str:
    url = os.environ.get("ASYNC_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "") or DATABASE_URL
    if not url:
        url = "sqlite+aiosqlite:///./data/math_ai.db"
        logger.warning(f"未配置数据库连接，使用默认SQLite: {url}")
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _get_sync_database_url() -> str:
    return DATABASE_URL or "sqlite:///./data/math_ai.db"


async def init_db() -> None:
    global engine, async_session_factory

    if engine is not None:
        await close_db()

    os.makedirs("data", exist_ok=True)

    db_url = _get_database_url()
    is_sqlite = "sqlite" in db_url

    connect_args = {}
    if is_sqlite:
        connect_args = {"check_same_thread": False}

    engine = create_async_engine(
        db_url,
        echo=False,
        **({"pool_size": 20, "max_overflow": 10, "pool_pre_ping": True} if not is_sqlite else {}),
        pool_recycle=3600,
        connect_args=connect_args,
    )

    if is_sqlite:
        from sqlalchemy import event as sa_event
        @sa_event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        import os as _os
        migration_path = _os.path.join(
            _os.path.dirname(__file__), "migrations", "003_add_user_skills.sql"
        )
        if _os.path.exists(migration_path):
            with open(migration_path, "r", encoding="utf-8") as f:
                migration_sql = f.read()
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: sync_conn.execute(
                        __import__("sqlalchemy").text(migration_sql)
                    )
                )
        logger.info("A03 user_skills 表迁移检查完成")
    except Exception as e:
        logger.warning(f"A03 迁移执行异常（表可能已存在）: {e}")

    logger.info(f"数据库初始化完成: {db_url.split('@')[-1] if '@' in db_url else db_url}")


async def close_db() -> None:
    global engine
    if engine:
        await engine.dispose()
        engine = None
        logger.info("数据库连接已关闭")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> dict:
    if engine is None:
        return {"status": "unhealthy", "error": "数据库未初始化"}

    try:
        async with engine.connect() as conn:
            start = time.time()
            await conn.execute(text("SELECT 1"))
            latency = (time.time() - start) * 1000

        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}