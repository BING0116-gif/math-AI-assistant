"""
Skill 功能实时验证 — 重启系统后运行此脚本查看数据是否入库

用法:
  1. 重启系统 (python main.py)
  2. 在聊天界面问 1-2 道数学题
  3. 运行此脚本: python scripts/check_skill_live.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")

def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("=" * 60)
    print("  SKILL 实时数据检查")
    print("=" * 60)

    # 1. learning_records 最新记录
    cur.execute("""
        SELECT id, user_id, event_type, category, sub_categories,
               difficulty, metadata, created_at
        FROM learning_records ORDER BY id DESC LIMIT 10
    """)
    rows = cur.fetchall()

    print(f"\n[1] 最近 {len(rows)} 条学习记录:")
    if rows:
        print(f"   {'ID':>5s} | {'User':20s} | {'Type':12s} | {'Cat':6s} | {'Sub':15s} | {'Diff':4s}")
        print(f"   {'-'*5}-+-{'-'*20}-+-{'-'*12}-+-{'-'*6}-+-{'-'*15}-+-{'-'*4}")
        for r in rows:
            uid = r[1][:18] + ".." if len(r[1]) > 20 else r[1]
            cat = r[3] or "-"
            sub = (r[4] or "-")[:13]
            diff = str(r[5]) if r[5] else "-"
            print(f"   {r[0]:5d} | {uid:20s} | {r[2]:12s} | {cat:6s} | {sub:15s} | {diff:>4s}")

        # 检查是否有 session_id 作为 user 的记录（说明 fallback 生效）
        session_users = [r for r in rows if r[1].startswith("23e64e50") or r[1] == "anonymous"]
        if session_users:
            print(f"\n   ★ 发现 {len(session_users)} 条使用 session_id 的记录（fallback 生效） [OK]")
        else:
            # 检查所有 user_id
            all_uids = set(r[1] for r in rows)
            print(f"\n   当前 user_ids: {list(all_uids)[:5]}")
    else:
        print("   [!] 没有任何学习记录！请先在聊天界面问一道数学题")

    # 2. user_skills 聚合结果
    cur.execute("SELECT COUNT(*) FROM user_skills")
    us_count = cur.fetchone()[0]

    print(f"\n[2] user_skills 表: {us_count} 个技能条目")

    if us_count > 0:
        cur.execute("""
            SELECT skill_code, display_name, mastery_level, status,
                   total_attempts, correct_count, user_id
            FROM user_skills ORDER BY mastery_level DESC LIMIT 10
        """)
        skills = cur.fetchall()
        print(f"   {'Status':10s} | {'Skill Name':25s} | Mastery | Attempts | User ID")
        print(f"   {'-'*10}-+-{'-'*25}-+---------+----------+----------------------------------")
        for s in skills:
            uid = (s[6] or "?")[:32]
            print(f"   {s[3]:10s} | {(s[1] or s[0]):25s} | {s[2]:7.3f} | {s[4]:8d} | {uid}")

        mastered = sum(1 for s in skills if s[3] == "mastered")
        print(f"\n   掌握: {mastered} | 熟练中: {sum(1 for s in skills if s[3]=='proficient')} | "
              f"学习中: {sum(1 for s in skills if s[3]=='learning')} | 新手: {sum(1 for s in skills if s[3]=='novice')}")
    else:
        print("   [!] 技能表为空。可能原因:")
        print("       a) 刚重启，还没有新的聊天请求经过 Skill 系统")
        print("       b) recalculate_skills 还没有被触发")
        print("")
        print("   → 解决方法: 运行 python scripts/manual_skill_test.py --action recalculate")

    # 3. 按 user_id 分组统计
    cur.execute("""
        SELECT user_id, COUNT(*), COUNT(CASE WHEN event_type='error_analysis' THEN 1 END)
        FROM learning_records GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 5
    """)
    by_user = cur.fetchall()

    print(f"\n[3] 按用户统计:")
    if by_user:
        print(f"   {'User ID':35s} | Total | Errors")
        print(f"   {'-'*35}-+-------+--------")
        for u in by_user:
            uid = u[0][:33] + ".." if len(u[0]) > 35 else u[0]
            print(f"   {uid:35s} | {u[1]:6d} | {u[2]:6d}")

    conn.close()

    print("\n" + "=" * 60)
    if us_count > 0 or rows:
        print("[RESULT] Skill system is WORKING - data in DB")
    else:
        print("[RESULT] No data yet - ask a question in chat then re-run")
    print("=" * 60)


if __name__ == "__main__":
    main()