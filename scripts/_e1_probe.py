# -*- coding: utf-8 -*-
"""临时只读探针：确认 math_ai_c3 当前内容生产基线（不修改任何数据）。"""
import os
import sys
import psycopg2

sys.stdout.reconfigure(encoding="utf-8")

URL = os.environ.get(
    "PG_SYNC_URL",
    "postgresql://mathai:mathai_test@localhost:5432/math_ai_c3",
)


def connect(dbname=None):
    import urllib.parse
    base = URL
    if dbname:
        base = base.rsplit("/", 1)[0] + "/" + dbname
    parts = urllib.parse.urlsplit(base)
    return psycopg2.connect(
        host=parts.hostname, port=parts.port or 5432,
        user=parts.username, password=parts.password,
        dbname=(parts.path or "/").lstrip("/"),
    )


def main():
    dbname = URL.rsplit("/", 1)[-1]
    con = connect()
    cur = con.cursor()
    print("DB:", dbname)

    cur.execute("select version_num from alembic_version")
    print("alembic_head:", cur.fetchone()[0])

    for table in ["questions", "content_import_candidates", "import_batches",
                  "source_documents", "knowledge_points", "question_knowledge_points"]:
        cur.execute(f'select count(*) from "{table}"')
        print(f"  count[{table}]:", cur.fetchone()[0])

    cur.execute("select review_status, count(*) from questions group by review_status order by review_status")
    print("questions_by_status:", dict(cur.fetchall()))

    cur.execute("select question_type, count(*) from questions group by question_type order by question_type")
    print("questions_by_type:", dict(cur.fetchall()))

    cur.execute("select status, count(*) from content_import_candidates group by status order by status")
    print("candidates_by_status:", dict(cur.fetchall()))

    cur.execute("select supported, count(*) from content_import_candidates group by supported")
    print("candidates_by_supported:", dict(cur.fetchall()))

    cur.execute(
        "select detected_question_type, count(*) from content_import_candidates "
        "group by detected_question_type order by detected_question_type"
    )
    print("candidates_by_type:", dict(cur.fetchall()))

    cur.execute(
        "select sd.original_filename, count(c.id) from source_documents sd "
        "left join import_batches ib on ib.source_document_id=sd.id "
        "left join content_import_candidates c on c.import_batch_id=ib.id "
        "group by sd.id, sd.original_filename order by sd.original_filename"
    )
    print("source_docs:", cur.fetchall())

    # drafts 详情
    cur.execute(
        "select id, question_type, length(answer), length(coalesce(analysis,'')), "
        "coalesce(source_candidate_id,'')<>'', is_ai_generated "
        "from questions where review_status in ('draft','reviewed') order by id"
    )
    print("draft/reviewed details:", cur.fetchall())

    cur.execute(
        "select q.id, count(qkp.knowledge_point_id) "
        "from questions q left join question_knowledge_points qkp on qkp.question_id=q.id "
        "group by q.id order by q.id"
    )
    print("questions kp_links:", cur.fetchall())

    con.close()


if __name__ == "__main__":
    main()
