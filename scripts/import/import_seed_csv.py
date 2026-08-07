"""从 CSV 导入种子题目到数据库（处理 content 字段含逗号的特殊格式）"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.data.models import Base, Question

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed_questions.csv")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def parse_csv_line(line: str):
    """
    自定义解析: 列顺序为
    id, content, question_type, options(quoted), answer(quoted), analysis(quoted),
    category(quoted), sub_categories(quoted), knowledge_points(quoted),
    difficulty, estimated_time, source
    """
    # 先找出所有双引号包裹的字段（fields 4-9，索引 3-8）
    # 这些是 options, answer, analysis, category, sub_categories, knowledge_points
    quoted_fields = []
    i = 0
    while i < len(line):
        if line[i] == '"':
            j = i + 1
            while j < len(line):
                if line[j] == '"':
                    if j + 1 < len(line) and line[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            quoted_fields.append((i, j, line[i + 1:j].replace('""', '"')))
            i = j + 1
        else:
            i += 1

    if len(quoted_fields) != 6:
        raise ValueError(f"期望 6 个引号字段，实际 {len(quoted_fields)} 个: {line[:100]}")

    # 第一个引号字段是 options，它之前的部分是: id, content, question_type
    first_quote_start = quoted_fields[0][0]
    prefix = line[:first_quote_start]
    prefix_parts = prefix.split(",")
    # prefix_parts: [id, content_part1, content_part2, ..., question_type, ""]
    qid = prefix_parts[0]
    question_type = prefix_parts[-2]  # 倒数第二个是 question_type（因为最后一个是空字符串）
    # 中间所有部分拼起来就是 content
    content = ",".join(prefix_parts[1:-2])

    # 提取 6 个引号字段
    options_str = quoted_fields[0][2]
    answer = quoted_fields[1][2]
    analysis = quoted_fields[2][2]
    category = quoted_fields[3][2]
    sub_categories = quoted_fields[4][2]
    knowledge_points_str = quoted_fields[5][2]

    # 最后一个引号字段之后的部分: difficulty, estimated_time, source
    last_quote_end = quoted_fields[5][1] + 1
    suffix = line[last_quote_end:].strip()
    suffix_parts = suffix.split(",")
    # 去掉开头的逗号分隔符后的空字符串
    if suffix_parts and suffix_parts[0] == "":
        suffix_parts = suffix_parts[1:]
    difficulty = int(suffix_parts[0])
    estimated_time = int(suffix_parts[1])
    source = suffix_parts[2] if len(suffix_parts) > 2 else ""

    return {
        "id": qid.strip(),
        "content": content.strip(),
        "question_type": question_type.strip(),
        "options": options_str,
        "answer": answer.strip(),
        "analysis": analysis.strip(),
        "category": category.strip(),
        "sub_categories": sub_categories.strip(),
        "knowledge_points": knowledge_points_str,
        "difficulty": difficulty,
        "estimated_time": estimated_time,
        "source": source.strip(),
    }


def import_csv():
    Base.metadata.create_all(engine)

    imported = 0
    skipped = 0
    failed = 0

    with Session(engine) as session:
        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()

        header = lines[0].strip()
        print(f"表头: {header}")
        print(f"数据行数: {len(lines) - 1}")
        print()

        for idx, line in enumerate(lines[1:], start=2):
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            try:
                row = parse_csv_line(line)
                qid = row["id"]
                if not qid:
                    failed += 1
                    continue

                existing = session.get(Question, qid)
                if existing:
                    skipped += 1
                    continue

                try:
                    options = json.loads(row["options"]) if row["options"] else []
                except (json.JSONDecodeError, TypeError):
                    options = []

                try:
                    knowledge_points = json.dumps(
                        json.loads(row["knowledge_points"]), ensure_ascii=False
                    ) if row["knowledge_points"] else "[]"
                except (json.JSONDecodeError, TypeError):
                    knowledge_points = row["knowledge_points"] or "[]"

                q = Question(
                    id=qid,
                    content=row["content"],
                    question_type=row["question_type"],
                    options=options,
                    answer=row["answer"],
                    analysis=row["analysis"],
                    category=row["category"],
                    sub_categories=row["sub_categories"],
                    knowledge_points=knowledge_points,
                    difficulty=row["difficulty"],
                    source=row["source"],
                    estimated_time=row["estimated_time"],
                    is_active=True,
                )
                session.add(q)
                imported += 1
                print(f"  导入: {qid} - {row['category']} - 难度{row['difficulty']} - {row['question_type']}")
            except Exception as e:
                failed += 1
                print(f"  失败 行{idx}: {e}")

        session.commit()

    print(f"\n完成! 导入: {imported}, 跳过(已存在): {skipped}, 失败: {failed}")


if __name__ == "__main__":
    import_csv()
