"""验证 user_id 是否正确贯穿 Agent → Strategy → Tool → RAG"""
import asyncio
import sys
import os

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, close_db


async def verify_user_id_chain():
    print("=" * 60)
    print("user_id 贯穿链路验证")
    print("=" * 60)

    await init_db()

    # 模拟一个真实用户ID
    test_user_id = "user_3783061912"  # 从截图看到的用户ID

    from agent_core.agent import MathAgent
    from app.config.settings import settings

    agent = MathAgent.create(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        base_url=settings.LLM_API_BASE,
        use_langchain_agent=True,
    )

    print(f"\n测试用户ID: {test_user_id}")
    print(f"请求: 给我出一道导数题")
    print(f"\n--- 开始 ---\n")

    chunk_count = 0
    chunks = []

    try:
        async for chunk in agent.stream(
            "给我出一道导数题",
            session_id="verify_uid_test",
            user_id=test_user_id,  # ← 传入真实用户ID
        ):
            chunk_count += 1
            chunks.append(chunk)

        full_text = "".join(chunks)
        print(f"\n{'='*60}")
        print(f"完成! chunks={chunk_count}, 长度={len(full_text)}")
        print(f"输出预览: {full_text[:300]}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    await close_db()


if __name__ == "__main__":
    asyncio.run(verify_user_id_chain())
