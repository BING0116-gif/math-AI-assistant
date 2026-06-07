"""查看题库中每道题的来源，区分PDF导入的题和种子测试数据"""
import asyncio
import sys
import os

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, get_db_session
from sqlalchemy import text


async def show_sources():
    await init_db()
    
    print("=" * 70)
    print("题库来源分析")
    print("=" * 70)
    
    async with get_db_session() as db:
        # 1. 总览：按 source 分组统计
        r = await db.execute(text("""
            SELECT COALESCE(source, '(无)'), COUNT(*) as cnt 
            FROM questions GROUP BY source ORDER BY cnt DESC
        """))
        rows = r.fetchall()
        
        total = sum(row[1] for row in rows)
        print(f"\n总题目数: {total}\n")
        print(f"{'来源':<35} {'数量':>6} {'占比':>8}")
        print("-" * 55)
        for src, cnt in rows:
            pct = cnt / total * 100 if total > 0 else 0
            print(f"{src:<35} {cnt:>6} {pct:>7.1f}%")
        
        # 2. 导数分类的详细列表（含ID、内容预览、来源）
        print("\n" + "=" * 70)
        print("导数分类 — 所有题目详情（前20条）")
        print("=" * 70)
        
        r = await db.execute(text("""
            SELECT id, substr(content, 80) as preview, category,
                   difficulty, source, created_at
            FROM questions WHERE category='导数' ORDER BY id LIMIT 20
        """))
        rows = r.fetchall()
        
        for row in rows:
            qid, preview, cat, diff, src, created = row
            # 标记来源类型
            tag = ""
            if src and "VL" in str(src):
                tag = "[PDF-VL导入]"
            elif src and "seed" in str(src).lower():
                tag = "[种子测试]"
            elif not src or src == "":
                tag = "[未知]"
            else:
                tag = f"[{src}]"
            
            print(f"\n{tag} ID={qid} | diff={diff}")
            print(f"   {preview}...")
        
        # 3. 随机抽3道PDF导入的题看完整内容
        print("\n" + "=" * 70)
        print("随机抽取 3 道 PDF-VL 导入的完整题目内容")
        print("=" * 70)
        
        r = await db.execute(text("""
            SELECT id, content, answer, source
            FROM questions WHERE source LIKE '%VL%' LIMIT 3
        """))
        rows = r.fetchall()
        
        for i, (qid, content, answer, src) in enumerate(rows):
            print(f"\n--- 第{i+1}题 [ID={qid}] 来源={src} ---")
            print(f"完整内容:\n{content[:400]}")
            if answer:
                print(f"\n答案: {answer}")


if __name__ == "__main__":
    asyncio.run(show_sources())
