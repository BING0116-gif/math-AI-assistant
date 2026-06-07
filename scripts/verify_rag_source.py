"""快速验证：RAG推荐结果是否包含完整的来源追踪信息"""
import asyncio
import sys
import os

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, close_db
from app.services.rag_recommender import get_rag_recommender, RecommendationRequest


async def main():
    await init_db()
    
    print("=" * 60)
    print("RAG 推荐结果 — 来源追踪验证")
    print("=" * 60)
    
    recommender = await get_rag_recommender()
    result = await recommender.recommend(RecommendationRequest(
        user_id="user_3783061912",
        target_category="导数",
        count=2,
        context="practice",
    ))
    
    print(f"\n推荐题目数: {len(result.questions)}")
    print(f"meta: {result.meta}")
    print()
    
    for i, q in enumerate(result.questions):
        print(f"--- 第{i+1}题 ---")
        print(f"  ID:       {q.get('id')}")
        print(f"  来源:     {q.get('source')}")
        print(f"  难度:     {q.get('difficulty')}")
        print(f"  分类:     {q.get('category')}")
        print(f"  内容预览: {q.get('content', '')[:150]}")
        print()
    
    if result.ai_analysis:
        print(f"AI分析: {list(result.ai_analysis.keys())}")
        if result.ai_analysis.get('recommendation_reason'):
            print(f"推荐理由: {result.ai_analysis['recommendation_reason'][:200]}")
    
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
