"""
RAG 推荐系统 -- 完整中文流程可视化

使用方法: python scripts/rag_demo.py
"""

import asyncio
import sys
import os
import time
import logging

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(message)s",
    datefmt="%H:%M:%S",
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)],
)


def print_banner():
    print("\n" + "=" * 60)
    print("   RAG 智能推荐系统 -- 完整流程演示")
    print("=" * 60)
    print()


async def main():
    print_banner()

    # 第1步：初始化数据库
    from app.data.database import init_db, close_db
    print("[第1步] 初始化数据库...")
    await init_db()
    print("  [OK] 数据库连接成功\n")

    # 第2步：查看题库现状
    from sqlalchemy import text
    from app.data.database import get_db_session
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT category, COUNT(*) as cnt FROM questions GROUP BY category ORDER BY cnt DESC")
        )
        rows = result.fetchall()
    
    total = sum(r[1] for r in rows)
    print(f"[第2步] 当前题库统计 (共 {total} 题):")
    for cat, cnt in rows:
        bar = "#" * min(cnt // 3, 30)
        print(f"  {cat:10s}  {cnt:4d} 题  {bar}")
    print()

    # 第3步：初始化 RAG 组件
    print("[第3步] 初始化 RAG 组件...")

    t0 = time.time()
    from app.services.vector_store import get_vector_store
    vs = await get_vector_store()
    t1 = time.time()
    doc_count = vs._collection.count()
    print(f"  [OK] 向量库就绪 ({doc_count} 个文档, 耗时{t1-t0:.1f}s)\n")

    t0 = time.time()
    from app.services.llm_service import get_llm_service
    llm = get_llm_service()
    t1 = time.time()
    print(f"  [OK] LLM 服务就绪 (耗时{t1-t0:.1f}s)\n")

    t0 = time.time()
    from app.services.rag_recommender import get_rag_recommender
    rag = await get_rag_recommender()
    t1 = time.time()
    print(f"  [OK] RAG 引擎就绪 (耗时{t1-t0:.1f}s)\n")

    # 第4步：执行推荐请求
    print("=" * 60)
    print("  模拟用户请求: 给我出两道导数题")
    print("=" * 60)
    print()

    from app.services.rag_recommender import RecommendationRequest
    
    req = RecommendationRequest(
        user_id="user_3783061912",
        target_category="导数",
        count=2,
        context="practice",
    )

    t_start = time.time()
    result = await rag.recommend(req)
    t_total = (time.time() - t_start) * 1000

    # 第5步：展示推荐结果
    print("\n" + "=" * 60)
    print("  推荐结果")
    print("=" * 60)

    meta = result.meta or {}
    print(f"\n  [统计]")
    print(f"     SQL精确检索   -> {meta.get('sql_result_count', '?')} 道")
    print(f"     向量语义搜索   -> {meta.get('vector_result_count', '?')} 道")
    print(f"     融合排序后取   -> {len(result.questions)} 道")
    print(f"     总耗时         -> {t_total:.0f}ms")
    print(f"     推荐难度       -> {meta.get('recommended_difficulty', '?')}/5")
    print(f"     检索方法       -> {meta.get('retrieval_method', '?')}")

    print(f"\n  [推荐题目] (来自你的 PDF 题库):\n")
    for i, q in enumerate(result.questions):
        qid = q.get('id', '?')
        src = q.get('source', '?')
        diff = q.get('difficulty', '?')
        content = q.get('content', '')
        
        print(f"  --- 第{i+1}题 ---")
        print(f"      ID:   {qid}")
        print(f"      来源: {src}")
        print(f"      难度: {diff}/5")
        print(f"      内容: {content[:200]}")
        print()

    if result.ai_analysis:
        ai = result.ai_analysis
        print(f"  [AI 学习建议]")
        if ai.get('assessment'):
            print(f"      能力评估: {ai['assessment'][:150]}")
        if ai.get('recommendation_reason'):
            print(f"      推荐理由: {ai['recommendation_reason'][:150]}")
        if ai.get('learning_advice'):
            print(f"      学习建议: {ai['learning_advice'][:150]}")
        print()

    print("=" * 60)
    print("  [完成] RAG 推荐流程结束! 以上题目均来自你的数据库。")
    print("=" * 60)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
