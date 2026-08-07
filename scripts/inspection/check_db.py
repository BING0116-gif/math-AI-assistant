"""检查数据库表状态。"""
import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "math_ai.db"))
print(f"DB path: {db_path}")
print(f"DB exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables in DB ({len(tables)}): {tables}")

# 测试创建表
conn.executescript("""
CREATE TABLE IF NOT EXISTS test_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
""")
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables after test create ({len(tables)}): {tables}")

conn.close()