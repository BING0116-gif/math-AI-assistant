"""完整链路诊断：模拟 Agent → Tool → RAG → 返回 的全过程"""
import asyncio
import sys
import os
import json
import time

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.base_tool import ToolInput, ToolOutput
from tools.recommend_tool import RecommendTool


async def diagnose_full_chain():
    print("=" * 60)
    print("完整调用链路诊断")
    print("=" * 60)

    # Step 0: 初始化数据库
    from app.data.database import init_db, close_db
    await init_db()

    # Step 1: 模拟 LangChain Adapter 调用工具（和真实Agent一样的方式）
    print("\n--- Step 1: 调用 recommend_questions 工具 ---")
    
    tool = RecommendTool()
    
    # 模拟 LangChain adapter 创建的 input_data（注意：没有user_id！）
    input_data = ToolInput(
        query="给我出两道导数题",
        parameters={"category": "导数", "count": 2, "context": "practice"},
        context={"source": "langchain_agent"},  # ← 这里没有 user_id!
    )
    
    start = time.time()
    try:
        result: ToolOutput = await tool.execute(input_data)
        elapsed = (time.time() - start) * 1000
        
        print(f"  工具执行耗时: {elapsed:.0f}ms")
        print(f"  success={result.success}")
        
        if result.success:
            print(f"  result长度: {len(result.result or '')} 字符")
            print(f"  result前200字: {result.result[:200]}")
            if result.data:
                questions = result.data.get("questions", [])
                print(f"  题目数: {len(questions)}")
                ai_analysis = result.data.get("ai_analysis", {})
                print(f"  AI分析字段: {list(ai_analysis.keys()) if ai_analysis else '(空)'}")
        else:
            print(f"  错误: {result.error}")
            
    except Exception as e:
        print(f"  异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 2: 检查返回给LLM的observation文本
    print("\n--- Step 2: 检查返回给LLM的格式 ---")
    if result.success:
        observation = str(result.result) if result.result else "执行成功"
        print(f"  observation长度: {len(observation)}")
        print(f"  observation内容:\n{observation[:500]}")
        
        # 检查是否有编码问题（中文能否正常显示）
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in observation)
        print(f"  包含中文: {has_chinese}")
        
        # 检查JSON序列化是否正常
        try:
            test_json = json.dumps({'content': observation}, ensure_ascii=False)
            print(f"  JSON序列化: OK ({len(test_json)}字符)")
        except Exception as e:
            print(f"  JSON序列化失败: {e}")

    # Step 3: 模拟 LLM 收到工具结果后的最终响应生成
    print("\n--- Step 3: 模拟LLM最终响应生成 ---")
    if result.success and result.result:
        from app.services.llm_service import get_llm_service
        
        llm = get_llm_service()
        
        prompt = f"""用户要求：给我出两道导数题

工具调用结果：
{result.result[:800]}

请基于以上推荐结果，用友好的语言向用户展示推荐的题目。只输出展示内容，不要加额外说明。"""
        
        start_llm = time.time()
        try:
            llm_response = await llm.generate(
                prompt=prompt,
                system_prompt="你是数学AI助手，帮学生推荐练习题。",
                temperature=0.3,
                max_tokens=1024,
            )
            llm_elapsed = (time.time() - start_llm) * 1000
            
            print(f"  LLM响应耗时: {llm_elapsed:.0f}ms")
            print(f"  响应长度: {len(llm_response.content)} 字符")
            print(f"  响应内容:\n{llm_response.content[:500]}")
            
        except Exception as e:
            print(f"  LLM调用失败: {type(e).__name__}: {e}")
    
    await close_db()
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(diagnose_full_chain())
