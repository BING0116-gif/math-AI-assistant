"""诊断推荐API为什么返回空"""
import asyncio
import sys
import os
import json

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag_recommender import get_rag_recommender, RecommendationRequest


async def diagnose():
    print("=" * 60)
    print("RAG 推荐引擎诊断")
    print("=" * 60)

    # 1. 初始化
    from app.data.database import init_db, close_db
    await init_db()

    # 2. 检查数据库中的导数题
    from app.data.database import get_db_session
    from sqlalchemy import text
    async with get_db_session() as db:
        r = await db.execute(text("SELECT COUNT(*) FROM questions WHERE category='导数'"))
        count = r.scalar()
        print(f"\n[DB] 导数分类题目数: {count}")

        r = await db.execute(text("""
            SELECT id, substr(content, 50) as preview, difficulty, source 
            FROM questions WHERE category='导数' LIMIT 5
        """))
        rows = r.fetchall()
        print(f"[DB] 前5道导数题:")
        for row in rows:
            print(f"  ID={row[0]} | diff={row[2]} | src={row[3]}")
            print(f"    {row[1]}")

    # 3. 检查向量库
    from app.services.vector_store import get_vector_store
    vs = await get_vector_store()
    try:
        stats = await vs.get_collection_stats()
        print(f"\n[Vector] 向量库统计: {stats}")
    except Exception as e:
        print(f"\n[Vector] 错误: {e}")

    # 4. 执行一次推荐
    print("\n--- 执行推荐 ---")
    recommender = await get_rag_recommender()
    
    try:
        result = await recommender.recommend(RecommendationRequest(
            user_id="test_user",
            target_category="导数",
            count=2,
            context="practice",
        ))
        
        print(f"\n[结果] 推荐成功!")
        print(f"  题目数量: {len(result.questions)}")
        print(f"  meta: {json.dumps(result.meta, ensure_ascii=False, indent=2)}")
        
        if result.questions:
            for i, q in enumerate(result.questions):
                print(f"\n  题{i+1}: {q.get('content', '')[:100]}...")
        
        if result.ai_analysis:
            print(f"\n  AI分析: {json.dumps(result.ai_analysis, ensure_ascii=False)[:200]}")
            
    except Exception as e:
        print(f"\n[错误] 推荐失败: {e}")
        import traceback
        traceback.print_exc()

    await close_db()


if __name__ == "__main__":
    asyncio.run(diagnose())
