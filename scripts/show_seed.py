"""查看 seed_questions.xlsx 的内容"""
import pandas as pd

df = pd.read_excel('data/seed_questions.xlsx')
print(f'=== seed_questions.xlsx 内容 ===')
print(f'共 {len(df)} 行, 列: {list(df.columns)}')
print()
for i, row in df.iterrows():
    qid = row.get('id', i+1)
    cat = row.get('category', '?')
    diff = row.get('difficulty', '?')
    content = str(row.get('content', ''))[:70]
    print(f'  [{qid}] {cat} | 难度{diff} | {content}')
