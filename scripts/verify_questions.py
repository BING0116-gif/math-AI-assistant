"""验证AI推荐的题目是否真的来自数据库"""
import asyncio
import sys
import os

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, get_db_session
from sqlalchemy import text


async def verify():
    await init_db()
    
    print("=" * 70)
    print("验证：AI推荐的题目是否在数据库中")
    print("=" * 70)

    async with get_db_session() as db:
        # AI输出的两道题的关键特征
        # 题目1: f(x) = x³-3x²+2x-1, 求导数在 x=1
        # 题目2: g(x) = e^x sin x, 求导数在 x=0
        
        # 1. 搜索包含这些特征的题目
        r = await db.execute(text("""
            SELECT id, content, source 
            FROM questions WHERE category='导数'
            AND (content LIKE '%x³%' OR content LIKE '%e^x%sin%' OR content LIKE '%sin%')
            LIMIT 10
        """))
        rows = r.fetchall()
        
        print(f"\n搜索包含 'x³' 或 'e^x sin' 或 'sin' 的导数题: {len(rows)} 条\n")
        
        for qid, content, src in rows:
            print(f"ID={qid} 来源={src}")
            print(f"内容: {content[:200]}")
            print("-" * 50)
        
        # 2. 显示所有包含 "f'(1)" 或 "g'(0)" 或 "求.*导" 的题目
        r2 = await db.execute(text("""
            SELECT id, content, answer, source
            FROM questions WHERE category='导数'
            AND content LIKE '%求%'
            ORDER BY id LIMIT 15
        """))
        rows2 = r2.fetchall()
        
        print(f"\n\n导数分类中含'求'字的题目（前15条）:\n")
        for qid, content, answer, src in rows2:
            print(f"[{qid}] {content[:120]}...")
            if answer:
                print(f"  → 答案: {answer}")
            print()

        # 3. 统计：RAG推荐时实际会返回哪些题目
        # 模拟SQL检索（按category=导数, difficulty=3）
        r3 = await db.execute(text("""
            SELECT id, substr(content, 100) as preview, difficulty, source
            FROM questions WHERE category='导数'
            AND difficulty=3 AND is_active=1
            ORDER BY RANDOM() LIMIT 5
        """))
        rows3 = r3.fetchall()
        
        print("\n" + "=" * 70)
        print("RAG SQL检索候选池（category=导数, difficulty=3）随机5条:")
        print("=" * 70)
        for qid, preview, diff, src in rows3:
            print(f"\n[{qid}] diff={diff} {src}")
            print(f"  {preview}...")


if __name__ == "__main__":
    asyncio.run(verify())
