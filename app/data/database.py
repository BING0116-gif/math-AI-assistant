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

# 数据库可达性标志：启动探测不可达时为 False，应用进入降级模式（其余服务仍可用）。
DB_AVAILABLE: bool = True


def is_database_available() -> bool:
    """返回当前数据库是否可用（启动时连通性探测结果）。"""
    return DB_AVAILABLE


def _get_database_url() -> str:
    # 异步引擎必须使用异步驱动。优先取显式异步 URL，再回退到同步 URL（下方自动补全 async 驱动）。
    # 注：pydantic-settings 不会把 .env 注入 os.environ，故 os.environ.get 常为空，需回退到模块级 ASYNC_DATABASE_URL。
    url = (
        os.environ.get("ASYNC_DATABASE_URL", "")
        or ASYNC_DATABASE_URL
        or os.environ.get("DATABASE_URL", "")
        or DATABASE_URL
        or ""
    )
    if not url:
        url = "sqlite+aiosqlite:///./data/math_ai.db"
        logger.warning(f"未配置数据库连接，使用默认SQLite: {url}")
    # 异步引擎要求异步驱动：缺失时根据库类型自动补全
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _get_sync_database_url() -> str:
    return DATABASE_URL or "sqlite:///./data/math_ai.db"


async def _run_alembic_migration(db_url: str) -> None:
    """使用 Alembic 执行数据库迁移。

    注意：必须用 `asyncio.to_thread + subprocess.run` 同步子进程，
    **不能**用 `asyncio.create_subprocess_exec` —— 在 Windows 上，
    uvicorn --reload 的 reloader 子进程里 asyncio 子循环不支持 subprocess，
    会直接抛 NotImplementedError，导致 lifespan 启动失败。
    """
    import asyncio
    import subprocess
    import sys

    # 获取同步 URL（Alembic 使用同步引擎）
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")

    env = os.environ.copy()
    env["DATABASE_URL"] = sync_url

    alembic_cfg = os.path.join(os.path.dirname(__file__), "alembic.ini")
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    def _invoke() -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", alembic_cfg, "upgrade", "head"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )

    # 在线程里跑同步子进程，避开 reload 子进程下 asyncio 子进程限制
    result = await asyncio.to_thread(_invoke)

    if result.returncode != 0:
        logger.error(f"Alembic 迁移失败: {result.stderr}")
        raise RuntimeError(f"数据库迁移失败: {result.stderr}")
    if result.stdout:
        # alembic 输出通常包含 INFO 行，转发给 logger
        for line in result.stdout.splitlines():
            logger.info("alembic: %s", line)
    logger.info("Alembic 迁移完成")


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
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # 轻量连通性探测：先确认数据库可达，再执行 Alembic 迁移。
    # 不可达时进入降级模式（应用仍可启动、AI 等非数据库功能可用），
    # 但绝不静默掩盖「可达之后的真实迁移逻辑错误」——迁移失败仍按原样抛出。
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as probe_err:  # 连接被拒 / 超时 / 凭证错误等
        global DB_AVAILABLE
        DB_AVAILABLE = False
        logger.warning(
            "数据库不可达，应用进入降级模式（SQL 功能暂不可用，其余服务正常）: %s",
            probe_err,
        )
        return

    # 使用 Alembic 替代 Base.metadata.create_all + 原始 SQL 迁移脚本
    await _run_alembic_migration(db_url)

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
    if not DB_AVAILABLE:
        return {
            "status": "degraded",
            "error": "数据库不可达，应用以降级模式运行",
        }

    try:
        async with engine.connect() as conn:
            start = time.time()
            await conn.execute(text("SELECT 1"))
            latency = (time.time() - start) * 1000

        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}