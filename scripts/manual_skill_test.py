"""
手动验证 Skill 机制 — 不依赖任何自测脚本

用法:
  1. 先运行一次: python scripts/manual_skill_test.py --action inject   (造10条模拟答题数据)
  2. 再运行一次: python scripts/manual_skill_test.py --action verify   (查看 user_skills 有没有被算出来)
  3. 可以反复修改下面 MOCK_DATA 中的数据，重新 inject + verify
"""

import sys
import os
import argparse
import sqlite3
import json
import asyncio

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEST_USER = "skill_verify_user_001"

MOCK_DATA = [
    {"question_content": "求极限 lim(x->0) sin(x)/x", "category": "极限", "sub_categories": "重要极限", "is_correct": True, "difficulty": 3, "time_spent": 90},
    {"question_content": "求导数 d/dx (x^3 + 2x)", "category": "导数", "sub_categories": "求导法则", "is_correct": True, "difficulty": 2, "time_spent": 60},
    {"question_content": "求积分 ∫ x^2 dx", "category": "积分", "sub_categories": "幂函数积分", "is_correct": False, "difficulty": 3, "time_spent": 180, "error_reason": "忘记加常数C"},
    {"question_content": "求导数 d/dx (sin(x))", "category": "导数", "sub_categories": "三角函数求导", "is_correct": True, "difficulty": 2, "time_spent": 45},
    {"question_content": "求极限 lim(x->inf) 1/x", "category": "极限", "sub_categories": "无穷极限", "is_correct": True, "difficulty": 2, "time_spent": 50},
    {"question_content": "解方程 x^2 - 5x + 6 = 0", "category": "代数", "sub_categories": "一元二次方程", "is_correct": True, "difficulty": 2, "time_spent": 70},
    {"question_content": "求积分 ∫ e^x dx", "category": "积分", "sub_categories": "指数函数积分", "is_correct": True, "difficulty": 3, "time_spent": 80},
    {"question_content": "化简 sin(2x) / (2*sin(x)*cos(x))", "category": "三角函数", "sub_categories": "二倍角公式", "is_correct": False, "difficulty": 4, "time_spent": 300, "error_reason": "二倍角公式记错"},
    {"question_content": "求 lim(x->0) (1+x)^(1/x)", "category": "极限", "sub_categories": "重要极限e", "is_correct": True, "difficulty": 4, "time_spent": 120},
    {"question_content": "求 ∫ cos(x) dx", "category": "积分", "sub_categories": "三角函数积分", "is_correct": True, "difficulty": 2, "time_spent": 55},
]


def action_inject():
    """直接往 SQLite 写入模拟的 learning_records"""
    db_path = os.path.join(PROJECT_ROOT, "data", "math_ai.db")
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        print("  Please run 'python -c \"from app.data.database import init_db; import asyncio; asyncio.run(init_db())\"' first")
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DELETE FROM learning_records WHERE user_id = ?", (TEST_USER,))
    deleted = cur.rowcount
    print(f"Cleaned {deleted} old records for user '{TEST_USER}'")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for i, data in enumerate(MOCK_DATA):
        cur.execute("""
            INSERT INTO learning_records (
                user_id, event_type, question_content, category,
                sub_categories, is_correct, difficulty, time_spent,
                error_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            TEST_USER,
            "answer_correct" if data["is_correct"] else "answer_wrong",
            data["question_content"],
            data["category"],
            data.get("sub_categories", ""),
            data["is_correct"],
            data.get("difficulty", 3),
            data.get("time_spent"),
            data.get("error_reason"),
            now.isoformat(),
        ))
        status = "OK" if data["is_correct"] else "WRONG"
        print(f"  [{i+1}/{len(MOCK_DATA)}] [{status:5s}] {data['category']:6s} | {data.get('sub_categories',''):15s} | {data['question_content'][:40]}")

    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM learning_records WHERE user_id = ?", (TEST_USER,)).fetchone()[0]
    correct = cur.execute("SELECT COUNT(*) FROM learning_records WHERE user_id = ? AND is_correct = 1", (TEST_USER,)).fetchone()[0]
    conn.close()

    print(f"\n[DONE] Injected {total} records ({correct} correct, {total-correct} wrong)")
    print(f"       User ID: {TEST_USER}")
    return True


async def action_recalculate():
    """调用 SkillAggregator 从 learning_records 重算 user_skills"""
    from app.data.database import init_db
    await init_db()

    from app.services.skill_aggregator import SkillAggregator
    agg = SkillAggregator()
    count = await agg.recalculate_skills(TEST_USER)
    print(f"[RECALCULATE] recalculate_skills wrote/updated {count} skill rows")
    return count > 0


def action_verify():
    """查数据库看结果"""
    db_path = os.path.join(PROJECT_ROOT, "data", "math_ai.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("=" * 60)
    print(f"SKILL VERIFICATION for user: {TEST_USER}")
    print("=" * 60)

    # 1. learning_records 原始数据
    cur.execute("SELECT COUNT(*) FROM learning_records WHERE user_id = ?", (TEST_USER,))
    lr_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM learning_records WHERE user_id = ? AND is_correct = 1", (TEST_USER,))
    lr_correct = cur.fetchone()[0]
    print(f"\n[1] learning_records: {lr_count} total, {lr_correct} correct")

    if lr_count == 0:
        print("\n[!] No learning_records found! Run '--action inject' first.")
        conn.close()
        return

    # 按分类统计
    cur.execute("""
        SELECT category, sub_categories,
               COUNT(*) as total,
               SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as correct
        FROM learning_records WHERE user_id = ?
        GROUP BY category, sub_categories ORDER BY category
    """, (TEST_USER,))
    rows = cur.fetchall()
    print(f"\n    {'Category':8s} | {'Sub-category':15s} | Total | Correct | Rate")
    print(f"    {'-'*8}-+-{'-'*15}-+-{'-'*5}-+-{'-'*7}-+-----")
    for r in rows:
        rate = r[3]/r[2] if r[2] else 0
        print(f"    {r[0]:8s} | {r[1]:15s} | {r[2]:5d} | {r[3]:7d} | {rate:.0%}")

    # 2. user_skills 计算结果
    cur.execute("SELECT COUNT(*) FROM user_skills WHERE user_id = ?", (TEST_USER,))
    us_count = cur.fetchone()[0]
    print(f"\n[2] user_skills: {us_count} skill entries calculated")

    if us_count == 0:
        print("\n[!!!] user_skills is EMPTY!")
        print("      This means SkillAggregator did NOT produce any output.")
        print("      Possible causes:")
        print("      a) You haven't run '--action recalculate' yet")
        print("      b) The aggregation logic has a bug")
        print("\n      Run: python scripts/manual_skill_test.py --action recalculate")
        conn.close()
        return

    cur.execute("""
        SELECT skill_code, display_name, mastery_level, status,
               total_attempts, correct_count,
               recent_streak, best_streak
        FROM user_skills WHERE user_id = ?
        ORDER BY mastery_level DESC
    """, (TEST_USER,))
    skills = cur.fetchall()

    print(f"\n    {'Status':10s} | {'Skill Code':30s} | Mastery | Attempts | Correct")
    print(f"    {'-'*10}-+-{'-'*30}-+---------+----------+---------")
    for s in skills:
        print(f"    {s[3]:10s} | {s[1]:30s} | {s[2]:7.3f} | {s[5]:8d} | {s[6]:7d}")

    # 3. 验证数据合理性
    print(f"\n[3] Data sanity checks:")
    has_nonzero_mastery = any(s[2] > 0 for s in skills)
    has_valid_status = all(s[3] in ('novice','learning','proficient','mastered') for s in skills)
    has_positive_attempts = all(s[5] > 0 for s in skills)

    checks = [
        ("mastery > 0 for some skills", has_nonzero_mastery),
        ("all statuses are valid", has_valid_status),
        ("all attempts > 0", has_positive_attempts),
        ("at least 1 skill exists", us_count >= 1),
    ]
    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[!!]"
        print(f"    {symbol} {name}: {status}")
        if not passed:
            all_pass = False

    print(f"\n{'=' * 60}")
    if all_pass:
        print("[RESULT] SKILL MECHANISM IS WORKING")
        print(f"         {us_count} skills calculated from {lr_count} learning events")
    else:
        print("[RESULT] SOME CHECKS FAILED — see [!!] items above")
    print(f"{'=' * 60}")

    conn.close()


async def main():
    parser = argparse.ArgumentParser(description="Manual Skill Mechanism Verification")
    parser.add_argument("--action", choices=["inject", "recalculate", "verify", "all"], default="all",
                        help="inject=造数据, recalculate=触发计算, verify=查看结果, all=全部执行")
    args = parser.parse_args()

    if args.action in ("inject", "all"):
        print("\n>>> Step 1: Injecting mock learning records...")
        action_inject()

    if args.action in ("recalculate", "all"):
        print("\n>>> Step 2: Running SkillAggregator.recalculate_skills()...")
        success = await action_recalculate()
        if not success:
            print("[WARNING] No skills were calculated")

    if args.action in ("verify", "all"):
        print("\n>>> Step 3: Verifying results...")
        action_verify()


if __name__ == "__main__":
    asyncio.run(main())