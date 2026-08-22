# -*- coding: utf-8 -*-
"""临时：列出 PostgreSQL 数据库与各库题目状态（不修改数据）。"""
import sys
import psycopg2

sys.stdout.reconfigure(encoding="utf-8")
HOST = "localhost"
PORT = 5432
USER = "mathai"
PWD = "mathai_test"


def list_dbs():
    con = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PWD, dbname="postgres")
    cur = con.cursor()
    cur.execute("select datname from pg_database where datistemplate=false order by datname")
    dbs = [r[0] for r in cur.fetchall()]
    con.close()
    return dbs


def snapshot(dbname):
    try:
        con = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PWD, dbname=dbname)
    except Exception as e:
        return f"connect error: {e}"
    cur = con.cursor()
    out = {}
    for table in ["questions", "knowledge_points", "question_knowledge_points",
                  "content_import_candidates", "import_batches", "source_documents"]:
        try:
            cur.execute(f'select count(*) from "{table}"')
            out[table] = cur.fetchone()[0]
        except Exception:
            out[table] = None
    try:
        cur.execute("select version_num from alembic_version")
        out["alembic_head"] = cur.fetchone()[0]
    except Exception:
        out["alembic_head"] = None
    try:
        cur.execute("select review_status, count(*) from questions group by review_status order by review_status")
        out["questions_by_status"] = dict(cur.fetchall())
    except Exception:
        out["questions_by_status"] = None
    con.close()
    return out


if __name__ == "__main__":
    dbs = list_dbs()
    print("DATABASES:", dbs)
    for db in dbs:
        if db.startswith("math_ai"):
            print(f"\n== {db} ==")
            snap = snapshot(db)
            for k, v in snap.items():
                print(f"  {k}: {v}")
