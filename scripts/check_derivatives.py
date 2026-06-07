"""查看导数分类的所有题目"""
import sqlite3
import json
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('data/math_ai.db')
c = conn.cursor()

print('=== 导数分类的所有题目 ===')
c.execute("SELECT id, substr(content,1,100), question_type, source, substr(answer,1,60) FROM questions WHERE category='导数' ORDER BY id")
rows = c.fetchall()
print(f'共 {len(rows)} 道导数题\n')
for row in rows:
    qid, content, qtype, source, answer = row
    print(f'ID={qid} | type={qtype} | src={source}')
    print(f'   content: {content}')
    print(f'   answer: {answer}')
    print()

# 也看看非PDF来源的导数题
print('\n=== 非PDF来源的导数题(原始种子数据) ===')
c.execute("SELECT id, substr(content,1,80), source FROM questions WHERE category='导数' AND (source='' OR source IS NULL OR source NOT LIKE '%PDF%') ORDER BY id")
for row in c.fetchall():
    print(f'  ID={row[0]} | src="{row[2]}" | {row[1]}')

print('\n=== PDF来源的导数题 ===')
c.execute("SELECT id, substr(content,1,80), source FROM questions WHERE category='导数' AND source LIKE '%PDF%' ORDER BY id")
for row in c.fetchall():
    print(f'  ID={row[0]} | src="{row[2]}" | {row[1]}')

conn.close()
