"""检查 Qdrant 向量库中实际存储了什么数据"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# 获取 collection 信息
info = client.get_collection("math_questions")
print(f"Collection: math_questions")
print(f"  总点数: {info.points_count}")
print(f"  状态: {info.status}")
print(f"  向量维度: {info.config.params.vectors.size}")
print()

# 滚动获取所有点，查看 payload 结构
points, next_offset = client.scroll(
    collection_name="math_questions",
    limit=5,
    with_payload=True,
    with_vectors=False,
)

print("=== 前5条数据的 payload 结构 ===")
for i, p in enumerate(points):
    payload = p.payload or {}
    print(f"\n--- Point {i+1} (id={p.id}) ---")
    for k, v in payload.items():
        val_str = str(v)
        if len(val_str) > 100:
            val_str = val_str[:100] + "..."
        print(f"  {k}: {val_str}")

# 统计所有点的 category 分布
print("\n\n=== 所有点的 category 分布 ===")
all_points, _ = client.scroll(
    collection_name="math_questions",
    limit=info.points_count,
    with_payload=True,
    with_vectors=False,
)

from collections import Counter
cats = Counter()
diffs = Counter()
has_content = 0
content_lengths = []

for p in all_points:
    payload = p.payload or {}
    cat = payload.get("category", "未知")
    diff = payload.get("difficulty", "?")
    content = payload.get("content", "")
    question_id = payload.get("question_id", str(p.id))

    cats[cat] += 1
    diffs[str(diff)] += 1
    if content:
        has_content += 1
        content_lengths.append(len(content))

print(f"总点数: {len(all_points)}")
print(f"有 content 字段: {has_content}")
if content_lengths:
    print(f"content 长度: 最小={min(content_lengths)}, 最大={max(content_lengths)}, 平均={sum(content_lengths)//len(content_lengths)}")

print(f"\nCategory 分布:")
for cat, count in cats.most_common():
    print(f"  {cat}: {count} 题")

print(f"\nDifficulty 分布:")
for diff, count in sorted(diffs.items()):
    print(f"  {diff}: {count} 题")

# 检查哪些 question_id 在 SQLite 中不存在
print("\n\n=== 检查 SQLite 同步情况 ===")
import sqlite3
conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "math_ai.db"))
cur = conn.cursor()
cur.execute("SELECT id FROM questions")
db_ids = set(row[0] for row in cur.fetchall())
conn.close()

qdrant_ids = set()
for p in all_points:
    payload = p.payload or {}
    qid = payload.get("question_id", str(p.id))
    qdrant_ids.add(qid)

in_both = db_ids & qdrant_ids
only_qdrant = qdrant_ids - db_ids
only_db = db_ids - qdrant_ids

print(f"SQLite 中有: {len(db_ids)} 题")
print(f"Qdrant 中有: {len(qdrant_ids)} 题")
print(f"两边都有: {len(in_both)} 题")
print(f"仅 Qdrant 有: {len(only_qdrant)} 题")
print(f"仅 SQLite 有: {len(only_db)} 题")

if only_qdrant:
    print(f"\n仅 Qdrant 有的题目 ID (前20个):")
    for qid in sorted(only_qdrant)[:20]:
        print(f"  {qid}")
