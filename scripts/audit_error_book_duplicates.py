# -*- coding: utf-8 -*-
"""错题本重复项只读审计。

用途：统计 error_items 中同一用户、同一题目文本的重复记录，量化修复前
可能已产生的“重复入库”污染面，供人工决定是否清理。**严格只读**：自建
异步 engine 仅执行 SELECT，绝不调用 init_db()（会跑 Alembic 迁移）、绝不
UPDATE/DELETE。输出会截断题目文本，避免整段内容进入日志。

使用：
    python scripts/audit_error_book_duplicates.py [--limit N] [--include-distinct]

默认连接 settings.ASYNC_DATABASE_URL / DATABASE_URL（与后端一致）。
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


def _async_url() -> str:
    url = (
        os.environ.get("ASYNC_DATABASE_URL", "")
        or getattr(__import__("app.config.settings", fromlist=["settings"]).settings, "ASYNC_DATABASE_URL", "")
        or os.environ.get("DATABASE_URL", "")
        or getattr(__import__("app.config.settings", fromlist=["settings"]).settings, "DATABASE_URL", "")
        or "sqlite:///./data/math_ai.db"
    )
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _norm(q: str) -> str:
    """题目标识归一：去 HTML/空白、小写，用于聚合疑似重复。"""
    if not q:
        return ""
    q = re.sub(r"<[^>]+>", " ", q)
    q = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "[图片]", q)
    return re.sub(r"\s+", " ", q).strip().lower()


async def audit(limit: int, include_distinct: bool) -> int:
    engine = create_async_engine(_async_url(), pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, user_id, item_id, question, question_type, correct_answer, "
                "error_reason, source, review_state, is_mastered, added_at "
                "FROM error_items ORDER BY user_id, added_at"
            ))).mappings().all()
    finally:
        await engine.dispose()

    backend = _async_url().split("://", 1)[0]
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["user_id"], _norm(r["question"]))].append(r)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    removable = sum(len(v) - 1 for v in dup_groups.values())

    print(f"数据库后端: {backend}")
    print(f"错题总行数: {len(rows)} | 去重后 (用户×题目) 组数: {len(groups)}")
    print(f"疑似重复组数: {len(dup_groups)} | 可回收冗余行(每组保留1条): {removable}")

    if not dup_groups:
        print("\n✅ 未发现同用户同题目的重复错题。")
        return 0

    # 仅“题目相同但原因/答案不同”的组标注为需人工确认，其余视为高置信重复
    print(f"\n疑似重复明细（最多显示 {limit} 组，题目截断 48 字）:\n")
    ordered = sorted(dup_groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    shown = 0
    for (user_id, qn), items in ordered:
        reasons = {(_norm(i["error_reason"]) or "(空)") for i in items}
        answers = {(_norm(i["correct_answer"]) or "(空)") for i in items}
        confidence = "高（原因与答案一致）" if len(reasons) == 1 and len(answers) == 1 else "中（原因/答案不同，需人工确认）"
        preview = (qn[:48] + "…") if len(qn) > 48 else (qn or "(空题目/图片)")
        ids = ", ".join(str(i["item_id"]) for i in items)
        print(f"- 用户 {user_id[:8]}… | 共 {len(items)} 条 | {confidence}")
        print(f"    题目: {preview}")
        print(f"    item_id: {ids}")
        shown += 1
        if shown >= limit:
            print(f"\n…（其余 {len(dup_groups) - shown} 组省略；--limit 调大）")
            break

    if include_distinct:
        print("\n注：本审计只读，不做任何修改。清理需另行授权并先备份。")
    print("\n（只读审计，未改动任何数据。）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="错题本重复项只读审计")
    p.add_argument("--limit", type=int, default=20, help="最多显示的重复组数（默认 20）")
    p.add_argument("--include-distinct", action="store_true", help="附加清理提示")
    args = p.parse_args()
    try:
        return asyncio.run(audit(args.limit, args.include_distinct))
    except Exception as e:  # 连接失败等：明确报错，绝不静默
        print(f"❌ 审计失败（未改动数据）：{type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
