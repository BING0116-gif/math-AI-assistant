# -*- coding: utf-8 -*-
"""Step 1.1-C3-R 只读调查：确认 'limit-laws' 来源是否为 dev DB stale data。

- 检查 knowledge_points 表是否存在 code=limit-laws
- 检查版本（演示版 vs 正式版）
- 检查是否生产代码/fixture 仍有引用
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "math_ai.db"


def main():
    if not DB.exists():
        print(f"ERROR: {DB} 不存在")
        return 1

    print(f"检查本地 SQLite dev DB: {DB}")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    # 检查 alembic 版本
    print("\n-- alembic_version --")
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        print(f"versions: {[r[0] for r in rows]}")
    except Exception as e:  # noqa: BLE001
        print(f"alembic_version 读取失败: {e}")

    # 检查 knowledge_points 中是否存在 limit-laws
    print("\n-- knowledge_points 搜索 'limit-laws' --")
    query = """
        SELECT code, name, version_id, id FROM knowledge_points WHERE code = ?
    """
    rows = conn.execute(query, ("limit-laws",)).fetchall()
    print(f"找到 {len(rows)} 行:")
    for code, name, version_id, row_id in rows:
        print(f"  code={code} name={name} version_id={version_id} id={row_id}")

    # 检查 limit-arithmetic-laws 状态
    print("\n-- 正式 code 确认 --")
    row = conn.execute(query, ("limit-arithmetic-laws",)).fetchone()
    if row:
        print(f"正式 code 'limit-arithmetic-laws' 存在: {row[0:3]}")
    else:
        print("WARNING: 正式 code 不存在")

    # 检查该 code 所属版本名称
    if rows:
        version_id = rows[0][2]
        vrow = conn.execute("SELECT version, name, status FROM knowledge_graph_versions WHERE id = ?",
                         (version_id,)).fetchone()
        if vrow:
            print(f"\n'limit-laws' 所属版本: version={vrow[0]} name={vrow[1]} status={vrow[2]}")

    conn.close()

    # 检查生产代码 grep
    print("\n-- 生产代码 grep --")
    import subprocess
    proc = subprocess.run(
        ["git", "grep", "-n", "limit-laws", "--", "*.py", "*.yml"],
        capture_output=True, text=True, cwd=ROOT,
    )
    lines = [l for l in proc.stdout.splitlines() if not l.startswith("scripts/")]
    if lines:
        print(f"生产代码中找到 {len(lines)} 行:")
        for l in lines:
            print(f"  {l}")
    else:
        print("生产代码中无匹配（除脚本注释）")

    print("\n-- 结论 --")
    if not rows:
        print("✓ dev DB 中不存在 'limit-laws' — 问题不存在")
    elif len(rows) == 1:
        print("✓ dev DB 中存在 'limit-laws' — 属于陈旧数据（演示版），生产代码已修正")
        print("  处理：修复 seed 函数跳过，不永久加入 alias；提供 dev DB 安全重置脚本")
    else:
        print("? 多个记录 — 需要进一步调查")

    return 0


if __name__ == "__main__":
    sys.exit(main())
