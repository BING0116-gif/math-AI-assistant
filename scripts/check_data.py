"""查看当前题库数据统计"""
import sqlite3
import os

db_path = "data/math_ai.db"
if not os.path.exists(db_path):
    print(f"数据库不存在: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 列出所有表
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"数据库表: {tables}")

# 查找题目相关表
for table in tables:
    if 'question' in table.lower() or 'q_' in table.lower():
        c.execute(f"SELECT COUNT(*) FROM [{table}]")
        count = c.fetchone()[0]
        print(f"\n=== 表 {table}: {count} 条记录 ===")
        # 看列名
        c.execute(f"PRAGMA table_info([{table}])")
        cols = [r[1] for r in c.fetchall()]
        print(f"  列: {cols}")

# 尝试 Question 表（SQLAlchemy 可能用不同命名）
for table in tables:
    try:
        c.execute(f"SELECT category, COUNT(*) as cnt FROM [{table}] GROUP BY category")
        rows = c.fetchall()
        if rows and len(rows[0]) == 2:
            print(f"\n--- {table} 按分类 ---")
            total = sum(r[1] for r in rows)
            print(f"  总计: {total} 题")
            for cat, cnt in rows:
                print(f"  {cat}: {cnt}题")
    except Exception:
        pass

# ChromaDB 统计
chroma_dir = "data/chroma_db"
if os.path.exists(chroma_dir):
    import chromadb
    client = chromadb.PersistentClient(path=chroma_dir)
    collections = client.list_collections()
    for coll in collections:
        count = coll.count()
        print(f"\n=== 向量库 {coll.name}: {count} 个文档 ===")
else:
    # 检查其他可能的 chroma 路径
    for root, dirs, files in os.walk("data"):
        if "chroma" in root.lower():
            print(f"\n发现向量库目录: {root}")

conn.close()
