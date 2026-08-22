# -*- coding: utf-8 -*-
"""临时只读探针 2：supported candidate 质量属性（original_answer/solution/page/warnings/KP）。"""
import os
import sys
import psycopg2

sys.stdout.reconfigure(encoding="utf-8")
URL = os.environ.get(
    "PG_SYNC_URL",
    "postgresql://mathai:mathai_test@localhost:5432/math_ai_c3",
)


def connect():
    import urllib.parse
    parts = urllib.parse.urlsplit(URL)
    return psycopg2.connect(
        host=parts.hostname, port=parts.port or 5432,
        user=parts.username, password=parts.password,
        dbname=(parts.path or "/").lstrip("/"),
    )


def main():
    con = connect()
    cur = con.cursor()

    # 45 supported：按 quality 属性统计
    cur.execute(
        """
        select
          coalesce(trim(original_answer),'') <> '' as has_answer,
          coalesce(trim(original_solution),'') <> '' as has_solution,
          source_page_start is not null and source_page_end is not null as has_page,
          coalesce(suggested_knowledge_point_codes::jsonb,'[]'::jsonb) = '[]'::jsonb as kp_pending,
          count(*)
        from content_import_candidates
        where supported = true and status <> 'imported'
        group by 1,2,3,4
        order by 5 desc
        """
    )
    print("supported (non-imported) quality combos:")
    for r in cur.fetchall():
        print("   answer=%s solution=%s page=%s kp_pending=%s n=%s" % r)

    # supported candidate 的 blocking warnings 分布
    cur.execute(
        """
        select w, count(*) from (
          select c.id, jsonb_array_elements_text(coalesce(c.warnings::jsonb,'[]'::jsonb)) as w
          from content_import_candidates c where c.supported=true and c.status <> 'imported'
        ) t group by w order by count(*) desc
        """
    )
    print("supported non-imported warning distribution:")
    for r in cur.fetchall():
        print("   ", r)

    # 无任何 warning 的 supported candidate 数
    cur.execute(
        """
        select count(*) from content_import_candidates
        where supported=true and status <> 'imported'
          and coalesce(jsonb_array_length(coalesce(warnings::jsonb,'[]'::jsonb)),0) = 0
        """
    )
    print("supported non-imported with zero warnings:", cur.fetchone()[0])

    # unsupported 明细：fill 需人工判定
    cur.execute(
        """
        select detected_question_type, count(*)
        from content_import_candidates where supported=false
        group by detected_question_type order by detected_question_type
        """
    )
    print("unsupported by type:", dict(cur.fetchall()))

    # candidate 状态 imported 的题目（已落 draft）
    cur.execute(
        """
        select c.id, c.detected_question_type, q.id, q.review_status,
               coalesce(trim(q.analysis),'')='' as analysis_empty,
               q.source_candidate_id
        from content_import_candidates c
        join questions q on q.source_candidate_id = c.id
        order by q.id
        """
    )
    print("imported -> question:")
    for r in cur.fetchall():
        print("   ", r)

    con.close()


if __name__ == "__main__":
    main()
