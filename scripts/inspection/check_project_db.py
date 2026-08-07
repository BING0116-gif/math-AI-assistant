import sqlite3
conn = sqlite3.connect('data/math_ai.db')
cur = conn.cursor()

# 检查表是否存在
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print('=== Tables ===')
for t in tables:
    print(t[0])

# 检查questions表数据
print()
cur.execute('SELECT COUNT(*) FROM questions')
total = cur.fetchone()[0]
print(f'=== Total rows in questions: {total} ===')

# 检查is_active分布
cur.execute('SELECT is_active, COUNT(*) FROM questions GROUP BY is_active')
for row in cur.fetchall():
    print(f'  is_active={row[0]}: {row[1]} rows')

# 看几条数据
cur.execute('SELECT id, category, difficulty, is_active FROM questions LIMIT 5')
rows = cur.fetchall()
print()
print('=== First 5 rows ===')
for r in rows:
    print(f'  id={r[0]}, category={r[1]}, difficulty={r[2]}, is_active={r[3]}')

conn.close()
