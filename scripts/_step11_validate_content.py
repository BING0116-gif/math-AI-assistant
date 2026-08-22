# -*- coding: utf-8 -*-
"""Step 1.1 内容完整性校验（可重复运行的审计脚本，只读）。

对已迁移的数据库执行：
- 统计知识点 / 题目总量与各审核状态数量
- 检查 published 题是否满足：answer 非空、explanation 非空、source 非空、>=1 知识点
- 检查知识点 code 非空、唯一、所属课程有效
- 输出：无知识点题 / 无答案题 / 无解析题 / 无来源题 / 重复知识点 code

用法：
    python scripts/_step11_validate_content.py [--db data/math_ai.db]
"""

import argparse
import json
import sqlite3
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/math_ai.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    def count(sql, *params) -> int:
        return cur.execute(sql, params).fetchone()[0]

    print("=" * 60)
    print("Step 1.1 内容完整性校验")
    print("=" * 60)

    # ── 知识点 ──
    kp_total = count("SELECT COUNT(*) FROM knowledge_points")
    kp_no_code = count("SELECT COUNT(*) FROM knowledge_points WHERE code IS NULL OR TRIM(code)=''")
    kp_dup_codes = cur.execute(
        "SELECT code, COUNT(*) c FROM knowledge_points GROUP BY code HAVING c > 1"
    ).fetchall()
    valid_courses = cur.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    kp_bad_course = count(
        "SELECT COUNT(*) FROM knowledge_points kp WHERE NOT EXISTS "
        "(SELECT 1 FROM courses c WHERE c.id = kp.course_id)"
    )
    print(f"知识点总数: {kp_total}")
    print(f"知识点无 code: {kp_no_code}")
    print(f"知识点重复 code: {len(kp_dup_codes)}")
    for r in kp_dup_codes:
        print(f"   重复 code: {r['code']} x{r['c']}")
    print(f"课程总数: {valid_courses}")
    print(f"知识点挂在无效课程: {kp_bad_course}")

    # ── 题目 ──
    q_total = count("SELECT COUNT(*) FROM questions")
    q_by_status = {
        st: count("SELECT COUNT(*) FROM questions WHERE review_status=?", st)
        for st in ("draft", "reviewed", "published", "retired")
    }
    # 无状态（迁移前遗留）题目数
    q_null_status = count("SELECT COUNT(*) FROM questions WHERE review_status IS NULL OR TRIM(review_status)=''")
    print(f"\n题目总数: {q_total}")
    print("  按审核状态:")
    for st, n in q_by_status.items():
        print(f"    {st}: {n}")
    print(f"  无审核状态(遗留): {q_null_status}")

    if q_total == 0:
        print("\n当前题库为空，跳过 published 字段完整性检查。")
        conn.close()
        return 0

    # published 必须字段完整
    pub = count("SELECT COUNT(*) FROM questions WHERE review_status='published'")
    pub_no_answer = count(
        "SELECT COUNT(*) FROM questions WHERE review_status='published' AND (answer IS NULL OR TRIM(answer)='')"
    )
    pub_no_analysis = count(
        "SELECT COUNT(*) FROM questions WHERE review_status='published' AND (analysis IS NULL OR TRIM(analysis)='')"
    )
    pub_no_source = count(
        "SELECT COUNT(*) FROM questions WHERE review_status='published' AND (source IS NULL OR TRIM(source)='')"
    )
    pub_no_kp = count(
        "SELECT COUNT(*) FROM questions q WHERE q.review_status='published' AND NOT EXISTS "
        "(SELECT 1 FROM question_knowledge_points qkp WHERE qkp.question_id=q.id)"
    )
    print(f"\npublished 题: {pub}")
    print(f"  published 无答案: {pub_no_answer}")
    print(f"  published 无解析: {pub_no_analysis}")
    print(f"  published 无来源: {pub_no_source}")
    print(f"  published 无知识点: {pub_no_kp}")

    # 全量无字段题（分状态）
    print("\n全量缺口统计:")
    print(f"  无答案题: {count('SELECT COUNT(*) FROM questions WHERE answer IS NULL OR TRIM(answer)=\"\"')}")
    print(f"  无解析题: {count('SELECT COUNT(*) FROM questions WHERE analysis IS NULL OR TRIM(analysis)=\"\"')}")
    print(f"  无来源题: {count('SELECT COUNT(*) FROM questions WHERE source IS NULL OR TRIM(source)=\"\"')}")
    print(f"  无知识点关联题: {count('SELECT COUNT(*) FROM questions q WHERE NOT EXISTS (SELECT 1 FROM question_knowledge_points qkp WHERE qkp.question_id=q.id)')}")

    # 校验失败即退出码 1
    failures = (kp_no_code + len(kp_dup_codes) + kp_bad_course
                + pub_no_answer + pub_no_analysis + pub_no_source + pub_no_kp)
    conn.close()

    print("\n" + ("校验通过" if failures == 0 else f"校验发现 {failures} 处问题"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())