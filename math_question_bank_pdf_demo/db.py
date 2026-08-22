import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "questions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,
    subject TEXT,
    grade TEXT,
    chapter TEXT,
    difficulty TEXT,
    question_type TEXT,
    stem_markdown TEXT NOT NULL,
    answer_markdown TEXT,
    solution_markdown TEXT,
    formulas_json TEXT,
    options_json TEXT,
    source_document TEXT,
    source_page INTEGER,
    review_status TEXT DEFAULT '待复核',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_chapter ON questions(chapter);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type);
"""

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
    print(f"数据库已初始化: {DB_PATH}")

def import_json(path):
    init_db()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON 顶层必须是数组，每个元素是一道题。")

    sql = """
    INSERT INTO questions (
        external_id, subject, grade, chapter, difficulty, question_type,
        stem_markdown, answer_markdown, solution_markdown,
        formulas_json, options_json, source_document, source_page,
        review_status, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(external_id) DO UPDATE SET
        subject=excluded.subject,
        grade=excluded.grade,
        chapter=excluded.chapter,
        difficulty=excluded.difficulty,
        question_type=excluded.question_type,
        stem_markdown=excluded.stem_markdown,
        answer_markdown=excluded.answer_markdown,
        solution_markdown=excluded.solution_markdown,
        formulas_json=excluded.formulas_json,
        options_json=excluded.options_json,
        source_document=excluded.source_document,
        source_page=excluded.source_page,
        review_status=excluded.review_status
    """
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        for q in data:
            conn.execute(sql, (
                q["external_id"],
                q.get("subject"),
                q.get("grade"),
                q.get("chapter"),
                q.get("difficulty"),
                q.get("question_type"),
                q.get("stem_markdown", ""),
                q.get("answer_markdown"),
                q.get("solution_markdown"),
                json.dumps(q.get("formulas", []), ensure_ascii=False),
                json.dumps(q.get("options", []), ensure_ascii=False),
                q.get("source_document"),
                q.get("source_page"),
                q.get("review_status", "待复核"),
                now,
            ))
    print(f"已导入/更新 {len(data)} 道题。")

def list_questions(args):
    init_db()
    clauses, params = [], []
    for field, value in [
        ("difficulty", args.difficulty),
        ("question_type", args.type),
        ("chapter", args.chapter),
        ("grade", args.grade),
    ]:
        if value:
            clauses.append(f"{field} = ?")
            params.append(value)
    if args.search:
        clauses.append("(stem_markdown LIKE ? OR answer_markdown LIKE ? OR solution_markdown LIKE ?)")
        kw = f"%{args.search}%"
        params.extend([kw, kw, kw])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT id, external_id, grade, chapter, difficulty, question_type, stem_markdown
        FROM questions {where}
        ORDER BY id LIMIT ?
    """
    params.append(args.limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        print("没有找到题目。")
        return

    for row in rows:
        stem = row["stem_markdown"].replace("\n", " ")
        if len(stem) > 70:
            stem = stem[:67] + "..."
        print(f'[{row["id"]}] {row["external_id"]} | {row["grade"]} | {row["chapter"]} | '
              f'{row["difficulty"]} | {row["question_type"]}')
        print(f"    {stem}")

def show_question(qid):
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    if not row:
        print(f"没有 ID={qid} 的题目。")
        return

    print("=" * 70)
    print(f'ID: {row["id"]} / {row["external_id"]}')
    print(f'年级: {row["grade"]} | 章节: {row["chapter"]} | 难度: {row["difficulty"]} | 类型: {row["question_type"]}')
    print(f'来源: {row["source_document"]} 第 {row["source_page"]} 页 | 状态: {row["review_status"]}')
    print("-" * 70)
    print("题目:")
    print(row["stem_markdown"])
    options = json.loads(row["options_json"] or "[]")
    if options:
        print("\n选项:")
        for opt in options:
            print("  " + opt)
    print("\n答案:")
    print(row["answer_markdown"] or "")
    print("\n解析:")
    print(row["solution_markdown"] or "")
    formulas = json.loads(row["formulas_json"] or "[]")
    if formulas:
        print("\nLaTeX 公式:")
        for f in formulas:
            print("  " + f)
    print("=" * 70)

def stats():
    init_db()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        print(f"题目总数: {total}")
        for title, field in [("按章节", "chapter"), ("按难度", "difficulty"), ("按题型", "question_type")]:
            print(f"\n{title}:")
            rows = conn.execute(
                f"SELECT COALESCE({field}, '未分类') AS k, COUNT(*) AS c "
                f"FROM questions GROUP BY {field} ORDER BY c DESC"
            ).fetchall()
            for r in rows:
                print(f"  {r['k']}: {r['c']}")

def reset():
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    print("数据库已重置。")

def main():
    parser = argparse.ArgumentParser(description="智能数学助手 - 本地题库 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    p_import = sub.add_parser("import", help="从 JSON 导入题目")
    p_import.add_argument("path")

    p_list = sub.add_parser("list", help="查看题目列表")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--difficulty")
    p_list.add_argument("--type")
    p_list.add_argument("--chapter")
    p_list.add_argument("--grade")
    p_list.add_argument("--search")

    p_show = sub.add_parser("show", help="查看某一道题")
    p_show.add_argument("id", type=int)

    sub.add_parser("stats", help="查看题库统计")
    sub.add_parser("reset", help="清空并重建数据库")

    args = parser.parse_args()
    if args.command == "init":
        init_db()
    elif args.command == "import":
        import_json(args.path)
    elif args.command == "list":
        list_questions(args)
    elif args.command == "show":
        show_question(args.id)
    elif args.command == "stats":
        stats()
    elif args.command == "reset":
        reset()

if __name__ == "__main__":
    main()
