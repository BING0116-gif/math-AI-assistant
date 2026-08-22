# -*- coding: utf-8 -*-
"""Step 1.1-C2 migration verification (SQLite + optional PostgreSQL).

用法：
    python scripts/_c2_migration_verify.py sqlite
    python scripts/_c2_migration_verify.py postgres

覆盖：
  - empty -> head
  - old head (e1f2a3b4c5d6) -> head
  - 校验新表 / 列 / index / unique / FK 存在
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
ALEMBIC_C = ROOT / "app" / "data" / "alembic.ini"
OLD_HEAD = "e1f2a3b4c5d6"
NEW_HEAD = "ab12cd34ef56"

PASS = "PASS"
FAIL = "FAIL"
_results = []


def report(section, ok, detail=""):
    _results.append((section, ok, detail))
    print(f"[{'✓' if ok else '✗'}] {section}  {detail}")


def run_alembic(database_url, target):
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_C), "upgrade", target],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180,
    )
    return proc


def check_sqlite(db_path):
    import sqlite3
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("select name from sqlite_master where type='table'")}
    report("SQLite 表: source_documents", "source_documents" in tables)
    report("SQLite 表: import_batches", "import_batches" in tables)
    report("SQLite 表: content_import_candidates", "content_import_candidates" in tables)
    q_cols = {r[1] for r in cur.execute("pragma table_info(questions)")}
    report("SQLite questions.source_candidate_id", "source_candidate_id" in q_cols)
    idx = {r[0] for r in cur.execute("select name from sqlite_master where type='index'")}
    report("SQLite 唯一索引 ix_questions_source_candidate_id", "ix_questions_source_candidate_id" in idx)
    # SQLite 的 UNIQUE 约束生成 autoindex；约束名出现在建表 SQL 中
    create_sql = next(r[0] for r in cur.execute(
        "select sql from sqlite_master where type='table' and name='import_batches'"))
    report("SQLite 唯一约束 uq_import_batch_idem", "uq_import_batch_idem" in (create_sql or ""))
    fks = [r[2] for r in cur.execute("pragma foreign_key_list(questions)")]
    report("SQLite questions->candidate FK", "content_import_candidates" in fks)
    con.close()


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "sqlite"
    tmp = Path(tempfile.mkdtemp(prefix="c2_mig_"))

    if kind == "sqlite":
        # empty -> head
        db1 = tmp / "empty.db"
        p1 = run_alembic(f"sqlite:///{db1}", "head")
        report(f"SQLite empty -> head (exit={p1.returncode})", p1.returncode == 0,
               p1.stderr.splitlines()[-1] if p1.stderr else "")
        if p1.returncode == 0:
            check_sqlite(db1)

        # old-head -> head
        db2 = tmp / "old.db"
        p_old = run_alembic(f"sqlite:///{db2}", OLD_HEAD)
        report(f"SQLite empty -> {OLD_HEAD} (exit={p_old.returncode})", p_old.returncode == 0)
        p2 = run_alembic(f"sqlite:///{db2}", "head")
        report(f"SQLite {OLD_HEAD} -> head (exit={p2.returncode})", p2.returncode == 0,
               p2.stderr.splitlines()[-1] if p2.stderr else "")
        if p2.returncode == 0:
            check_sqlite(db2)

    elif kind == "postgres":
        pg_sync = os.environ.get("PG_SYNC_URL", "postgresql://mathai:mathai_test@localhost:5432/math_ai_empty")
        # empty -> head
        p1 = run_alembic(pg_sync, "head")
        report(f"PostgreSQL empty -> head (exit={p1.returncode})", p1.returncode == 0,
               p1.stderr.splitlines()[-1] if p1.stderr else "")
        # old-head -> head
        p_old = run_alembic(pg_sync, OLD_HEAD)
        report(f"PostgreSQL downgrade to {OLD_HEAD} (exit={p_old.returncode})", p_old.returncode == 0,
               p_old.stderr.splitlines()[-1] if p_old.stderr else "")
        p2 = run_alembic(pg_sync, "head")
        report(f"PostgreSQL {OLD_HEAD} -> head (exit={p2.returncode})", p2.returncode == 0,
               p2.stderr.splitlines()[-1] if p2.stderr else "")

    ok = all(x[1] for x in _results)
    print("\n== RESULT:", "ALL PASS" if ok else "HAS FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()