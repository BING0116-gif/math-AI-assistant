# -*- coding: utf-8 -*-
"""Dev-only：安全重建本地 SQLite 开发数据库（默认 data/math_ai.db）。

使用场景（Step 1.1-C3-R）：知识体系 schema/code 发生不兼容变化后（例如
`limit-laws` -> `limit-arithmetic-laws`），本地 SQLite dev DB 残留陈旧
KnowledgePoint code，导致 app lifespan 启动 KeyError。

原则（AGENTS.md）：
- data/math_ai.db 是 git-ignored 的可重建本地开发缓存；正式事实来源是 PostgreSQL。
- 不在 app startup 自动 destructive reset；本脚本只由开发者手动调用。
- 不允许手工 `sqlite3 ... UPDATE` 篡改 DB；一律通过「备份 -> 删除 -> alembic
  upgrade head -> seed 正式 catalog」的可重复流程重建。

安全约束（Step 1.1-C3-R §14）：
- 仅限本地 SQLite；默认拒绝 PostgreSQL 目标（防止误删生产数据库）。
- 打印目标 DB；要求显式 `--yes`（或交互确认）。
- 重建前备份到 data/backups/（可用 `--no-backup` 关闭，不推荐）。

用法：
    python scripts/reset_dev_db.py                       # 交互确认
    python scripts/reset_dev_db.py --yes                 # 跳过确认
    python scripts/reset_dev_db.py --db data/math_ai.db --yes
    python scripts/reset_dev_db.py --dry-run             # 只打印将做什么，不执行
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "data" / "math_ai.db"
BACKUP_DIR = ROOT / "data" / "backups"

SQLITE_PREFIXES = ("sqlite:///", "sqlite+aiosqlite:///")
PG_PREFIXES = ("postgresql://", "postgresql+asyncpg://")


def _extract_sqlite_path(url: str) -> Path:
    """把 sqlite:///path 或 sqlite+aiosqlite:///path 解析为本地路径。"""
    for prefix in SQLITE_PREFIXES:
        if url.startswith(prefix):
            p = url[len(prefix):]
            p = p.replace("\\", "/")
            # sqlite:////abs/path -> /abs/path；sqlite:///./data/x -> ./data/x
            if p.startswith("/") and not p.startswith("//"):
                p = p[1:]
            return Path(p)
    raise ValueError(f"不是 SQLite URL: {url[:40]}")


def _resolve_target_db(args) -> Path:
    """决定目标 DB：--db 优先；否则看 DATABASE_URL env；否则默认 data/math_ai.db。"""
    if args.db:
        return Path(args.db).expanduser().resolve()
    env_url = os.environ.get("ASYNC_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
    if env_url:
        if env_url.startswith(PG_PREFIXES):
            # 默认拒绝 PostgreSQL：绝不把生产/开发 PG 当 SQLite 重建
            raise SystemExit(
                f"[abort] 检测到 PostgreSQL 目标（{env_url.split('@')[-1]}）。\n"
                "本脚本仅用于重建本地 SQLite dev DB。若确需操作 SQLite，请显式传入 "
                "--db data/math_ai.db 并先移除 DATABASE_URL/ASYNC_DATABASE_URL。"
            )
        if env_url.startswith(SQLITE_PREFIXES):
            return _extract_sqlite_path(env_url).expanduser().resolve()
        raise SystemExit(f"[abort] 无法识别的数据库 URL：{env_url[:40]}")
    return DEFAULT_DB


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


async def _rebuild(db_path: Path, with_backup: bool, dry_run: bool) -> None:
    # 备份（仅 SQLite 主文件 + WAL/SHM）
    if with_backup and not dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"math_ai_{ts}.db"
        shutil.copy2(db_path, dest)
        for suffix in ("-wal", "-shm"):
            s = Path(str(db_path) + suffix)
            if s.exists():
                shutil.copy2(s, BACKUP_DIR / f"math_ai_{ts}.db{suffix}")
        print(f"[backup] {db_path} -> {dest}")

    if dry_run:
        print(f"[dry-run] 将删除 {db_path}（及 -wal/-shm），然后 alembic upgrade head + seed 正式 catalog")
        return

    # 删除
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
            print(f"[removed] {p}")

    # 强制走本地 SQLite（屏蔽可能存在的 PG env）
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("ASYNC_DATABASE_URL", None)
    os.environ["AI_ENABLED"] = "false"
    # 使用绝对路径，避免 cwd 差异
    url = "sqlite+aiosqlite:///" + str(db_path).replace("\\", "/")
    os.environ["ASYNC_DATABASE_URL"] = url
    os.environ["DATABASE_URL"] = url.replace("+aiosqlite", "", 1)

    # 此处再 import app（settings 于 import 时读取 env）
    from sqlalchemy import select

    from app.data.database import close_db, get_db_session, init_db
    from app.data.models import KnowledgePoint
    from app.services.knowledge_seed import seed_phase_one_calculus

    print("[step] alembic upgrade head ...")
    await init_db()
    print("[step] seed 正式 catalog ...")
    async with get_db_session() as db:
        await seed_phase_one_calculus(db)
    # 验证：正式 24 code 存在，且无 limit-laws 残留
    async with get_db_session() as db:
        codes = set((await db.execute(select(KnowledgePoint.code))).scalars().all())
    await close_db()
    stale = codes & {"limit-laws"}
    official = {"limit-arithmetic-laws"}.issubset(codes)
    print(f"[verify] KnowledgePoint codes={len(codes)}  limit-arithmetic-laws 存在={official}")
    if stale:
        raise SystemExit(f"[verify-fail] 仍存在陈旧 code: {stale}")
    if not official:
        raise SystemExit("[verify-fail] 正式 catalog 未正确 seed（缺 limit-arithmetic-laws）")
    print("[done] 本地 SQLite dev DB 重建完成（PostgreSQL 未被触碰）")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev-only：重建本地 SQLite 开发数据库")
    parser.add_argument("--db", default=None, help="SQLite DB 路径（默认 data/math_ai.db）")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    parser.add_argument("--no-backup", action="store_true", help="不备份（不推荐）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作")
    args = parser.parse_args()

    try:
        db_path = _resolve_target_db(args)
    except SystemExit as e:
        print(e)
        return 2

    if not db_path.name.endswith(".db"):
        print(f"[abort] 目标不是 .db 文件：{db_path}")
        return 2

    print(f"[target] 将要重建的本地 SQLite dev DB：{db_path}")
    print(f"[target] 存在={db_path.exists()} 大小={db_path.stat().st_size if db_path.exists() else 0}B")
    if not _confirm("确认重建（会删除该本地 dev DB 并重新迁移+seed）？", args.yes):
        print("[abort] 已取消")
        return 0

    if args.dry_run:
        asyncio.run(_rebuild(db_path, not args.no_backup, True))
        return 0

    if not db_path.exists():
        print(f"[abort] 目标 DB 不存在，无需重建：{db_path}")
        return 0

    asyncio.run(_rebuild(db_path, not args.no_backup, False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
