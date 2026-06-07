"""诊断 LangChain Agent 内部事件流 — 看 astream_events 到底发了什么"""
import asyncio
import sys
import os
import json
import time

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import init_db, close_db


async def diagnose_agent_events():
    print("=" * 60)
    print("LangChain Agent 内部事件流诊断")
    print("=" * 60)

    await init_db()

    # 复用 Agent 的初始化逻辑
    from agent_core.agent import MathAgent
    from app.config.settings import settings
    
    # 初始化 Agent（和 main.py 一样的方式）
    agent = MathAgent(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        base_url=settings.LLM_API_BASE,
        use_langchain_agent=True,
    )
    
    user_input = "给我出两道导数题"
    session_id = "diag_test_session"
    
    print(f"\n输入: {user_input}")
    print(f"Session: {session_id}")
    print(f"\n--- 开始 Agent.stream() ---\n")
    
    start = time.time()
    chunk_count = 0
    all_event_types = {}
    chunks_content = []
    
    try:
        async for chunk in agent.stream(user_input, session_id=session_id):
            chunk_count += 1
            chunks_content.append(chunk)
            
            # 显示每个chunk的信息
            preview = chunk.replace('\n', '\\n')[:80]
            print(f"  chunk#{chunk_count} [{len(chunk)}ch]: {preview}...")
        
        elapsed = (time.time() - start) * 1000
        
        full_text = "".join(chunks_content)
        print(f"\n{'='*60}")
        print(f"Agent.stream() 完成:")
        print(f"  总chunks: {chunk_count}")
        print(f"  总长度: {len(full_text)} 字符")
        print(f"  总耗时: {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
        print(f"\n完整输出:\n{full_text}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    await close_db()


if __name__ == "__main__":
    asyncio.run(diagnose_agent_events())
