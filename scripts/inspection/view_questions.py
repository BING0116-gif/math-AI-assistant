"""
查看数据库中题目的脚本
用法:
  python scripts/inspection/view_questions.py                    # 查看所有题目（分页）
  python scripts/inspection/view_questions.py --category 函数     # 按分类筛选
  python scripts/inspection/view_questions.py --difficulty 3      # 按难度筛选 (1-5)
  python scripts/inspection/view_questions.py --type 选择题       # 按题型筛选
  python scripts/inspection/view_questions.py --id Q001           # 按 ID 精确查找
  python scripts/inspection/view_questions.py --detail            # 显示完整详情（含解析）
  python scripts/inspection/view_questions.py --stats             # 显示统计信息
"""

import argparse
import json
import os
import sys
import textwrap

# 将项目根目录加入路径，确保能导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from app.data.models import Question

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")
SYNC_URL = f"sqlite:///{DB_PATH}"

DIFFICULTY_MAP = {1: "入门", 2: "基础", 3: "标准", 4: "进阶", 5: "挑战"}


def get_session() -> Session:
    engine = create_engine(SYNC_URL, connect_args={"check_same_thread": False})
    return Session(engine)


def print_separator(char="-", width=80):
    print(char * width)


def print_question(q: Question, index: int = 0, detail: bool = False):
    """打印单条题目信息"""
    prefix = f"[{index}] " if index > 0 else ""
    diff_label = DIFFICULTY_MAP.get(q.difficulty, str(q.difficulty))

    print()
    print_separator("=")
    print(f"  {prefix}ID: {q.id}")
    print(f"  分类: {q.category}  |  题型: {q.question_type}  |  难度: {q.difficulty}({diff_label})")
    if q.sub_categories:
        print(f"  子分类: {q.sub_categories}")
    if q.knowledge_points:
        try:
            kp = json.loads(q.knowledge_points) if isinstance(q.knowledge_points, str) else q.knowledge_points
            print(f"  知识点: {', '.join(kp) if isinstance(kp, list) else kp}")
        except Exception:
            print(f"  知识点: {q.knowledge_points}")
    print(f"  预估时间: {q.estimated_time}分钟  |  使用次数: {q.usage_count}  |  正确率: {q.correct_rate:.1%}" if q.correct_rate else f"  预估时间: {q.estimated_time}分钟")
    print_separator("-")

    # 题目内容（自动换行）
    content = q.content or "(空)"
    print(f"  [题目]")
    for line in content.split("\n"):
        print(textwrap.fill(line, width=76, initial_indent="    ", subsequent_indent="    "))

    # 选项
    if q.options:
        opts = q.options if isinstance(q.options, dict) else json.loads(q.options) if isinstance(q.options, str) else {}
        if opts:
            print("  [选项]")
            for key, val in opts.items():
                print(f"    {key}. {val}")

    # 答案
    print(f"\n  [答案] {q.answer}")

    # 详情模式：显示解析和解答步骤
    if detail:
        if q.analysis:
            print(f"\n  [解析]")
            for line in q.analysis.split("\n"):
                print(textwrap.fill(line, width=76, initial_indent="    ", subsequent_intent="    "))
        if q.solution_steps:
            steps = q.solution_steps if isinstance(q.solution_steps, list) else json.loads(q.solution_steps) if isinstance(q.solution_steps, str) else []
            if steps:
                print(f"\n  [解题步骤]")
                for i, step in enumerate(steps, 1):
                    print(f"    步骤{i}: {step}")

    print()


def show_stats(session: Session):
    """显示统计信息"""
    total = session.execute(select(func.count(Question.id))).scalar()

    # 按分类统计
    cat_stats = session.execute(
        select(Question.category, func.count(Question.id)).group_by(Question.category).order_by(func.count(Question.id).desc())
    ).all()

    # 按难度统计
    diff_stats = session.execute(
        select(Question.difficulty, func.count(Question.id)).group_by(Question.difficulty).order_by(Question.difficulty)
    ).all()

    # 按题型统计
    type_stats = session.execute(
        select(Question.question_type, func.count(Question.id)).group_by(Question.question_type).order_by(func.count(Question.id).desc())
    ).all()

    print_separator("=")
    print(f"  数据库题目统计总览")
    print_separator("=")
    print(f"  总题数: {total}")
    print()

    print(f"  --- 按分类 ---")
    for cat, count in cat_stats:
        print(f"    {cat}: {count} 题")

    print(f"\n  --- 按难度 ---")
    for diff, count in diff_stats:
        label = DIFFICULTY_MAP.get(diff, str(diff))
        print(f"    {diff}({label}): {count} 题")

    print(f"\n  --- 按题型 ---")
    for qt, count in type_stats:
        print(f"    {qt}: {count} 题")

    print()


def list_questions(session: Session, args):
    """列出符合条件的题目"""
    query = select(Question).where(Question.is_active == True).order_by(Question.category, Question.difficulty, Question.id)

    if args.id:
        query = query.where(Question.id == args.id)
    if args.category:
        query = query.where(Question.category.contains(args.category))
    if args.difficulty:
        query = query.where(Question.difficulty == args.difficulty)
    if args.type:
        query = query.where(Question.question_type.contains(args.type))

    results = session.execute(query).scalars().all()

    if not results:
        print("\n  未找到匹配的题目。")
        return

    total = len(results)
    page_size = args.limit or 10
    total_pages = (total + page_size - 1) // page_size
    page = args.page or 1

    start = (page - 1) * page_size
    end = start + page_size
    page_items = results[start:end]

    print(f"\n  共找到 {total} 道题目  (第 {page}/{total_pages} 页, 每页 {page_size} 条)")
    if args.category:
        print(f"  筛选条件: 分类包含 '{args.category}'")
    if args.difficulty:
        print(f"  筛选条件: 难度 = {args.difficulty}({DIFFICULTY_MAP.get(args.difficulty, '')})")
    if args.type:
        print(f"  筛选条件: 题型包含 '{args.type}'")
    if args.id:
        print(f"  筛选条件: ID = '{args.id}'")

    for i, q in enumerate(page_items, start=start + 1):
        print_question(q, index=i, detail=args.detail)

    if total_pages > 1:
        print(f"  --- 提示: 使用 --page {page + 1} 查看下一页 ---")


def main():
    parser = argparse.ArgumentParser(description="查看数学AI助手数据库中的题目")
    parser.add_argument("--id", type=str, help="按题目ID精确查找")
    parser.add_argument("--category", "-c", type=str, help="按分类名称模糊筛选")
    parser.add_argument("--difficulty", "-d", type=int, choices=[1, 2, 3, 4, 5], help="按难度筛选 (1-5)")
    parser.add_argument("--type", "-t", type=str, help="按题型模糊筛选")
    parser.add_argument("--detail", action="store_true", help="显示完整详情（含解析和步骤）")
    parser.add_argument("--stats", "-s", action="store_true", help="显示统计信息")
    parser.add_argument("--page", "-p", type=int, default=1, help="页码 (默认1)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="每页条数 (默认10)")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"错误: 数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    session = get_session()
    try:
        if args.stats:
            show_stats(session)
        else:
            list_questions(session, args)
    finally:
        session.close()


if __name__ == "__main__":
    main()
