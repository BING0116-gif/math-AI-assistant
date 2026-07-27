"""将 Qdrant 向量库中的 176 题同步到 SQLite 数据库"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.data.models import Base, Question

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "math_ai.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

client = QdrantClient(host="localhost", port=6333)

# 获取所有点
info = client.get_collection("math_questions")
total = info.points_count
print(f"Qdrant 总点数: {total}")

all_points = []
offset = None
while True:
    points, next_offset = client.scroll(
        collection_name="math_questions",
        limit=500,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    all_points.extend(points)
    if next_offset is None:
        break
    offset = next_offset

print(f"已读取 {len(all_points)} 个点")

imported = 0
skipped = 0
failed = 0

with Session(engine) as session:
    for p in all_points:
        payload = p.payload or {}
        qid = payload.get("question_id", str(p.id))

        # 检查是否已存在
        existing = session.get(Question, qid)
        if existing:
            skipped += 1
            continue

        try:
            content = payload.get("content", "")
            if not content:
                failed += 1
                print(f"  跳过 {qid}: content 为空")
                continue

            # 解析 knowledge_points
            kp_raw = payload.get("knowledge_points", "[]")
            if isinstance(kp_raw, str):
                try:
                    knowledge_points = json.dumps(json.loads(kp_raw), ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    knowledge_points = kp_raw
            else:
                knowledge_points = json.dumps(kp_raw, ensure_ascii=False) if kp_raw else "[]"

            q = Question(
                id=qid,
                content=content,
                question_type=payload.get("question_type", "text") or "text",
                options=payload.get("options", []),
                answer=payload.get("answer", "") or "",
                analysis=payload.get("analysis", "") or "",
                category=payload.get("category", "未知") or "未知",
                sub_categories=payload.get("sub_categories", "") or "",
                knowledge_points=knowledge_points,
                difficulty=int(payload.get("difficulty", 3) or 3),
                source=payload.get("source", "") or "",
                estimated_time=int(payload.get("estimated_time", 5) or 5),
                is_active=True,
            )
            session.add(q)
            imported += 1
        except Exception as e:
            failed += 1
            print(f"  失败 {qid}: {e}")

    session.commit()

print(f"\n完成! 导入: {imported}, 跳过(已存在): {skipped}, 失败: {failed}")
print(f"SQLite 现在应该有 {imported + skipped} 题（来自 Qdrant）+ 原有 20 题")
