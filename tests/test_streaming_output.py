"""
流式输出测试脚本

验证打字机效果的实现。
"""

import sys
import os
import asyncio
import time

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


async def test_streaming_chat():
    """测试流式聊天响应。"""
    print("=" * 60)
    print("流式输出测试 - 聊天模式")
    print("=" * 60)

    from main import agent

    print("\n发送测试消息: '你好，请介绍一下自己'")
    print("-" * 40)
    print("输出: ", end="", flush=True)

    start_time = time.time()
    char_count = 0
    last_update = start_time

    async for chunk in agent.stream("你好，请介绍一下自己"):
        if chunk:
            print(chunk, end="", flush=True)
            char_count += 1

            # 每秒显示进度
            now = time.time()
            if now - last_update >= 1.0:
                elapsed = now - start_time
                speed = char_count / elapsed
                print(f"\n[进度] {char_count} 字, {elapsed:.1f}秒, {speed:.1f} 字/秒", end="", flush=True)
                last_update = now

    elapsed = time.time() - start_time
    print(f"\n\n[完成] 总计 {char_count} 字, 耗时 {elapsed:.1f}秒")
    print(f"[速度] 平均 {char_count / elapsed:.1f} 字/秒")


async def test_streaming_math():
    """测试数学问题流式输出。"""
    print("\n" + "=" * 60)
    print("流式输出测试 - 数学问题")
    print("=" * 60)

    from main import agent

    question = "求函数 f(x) = x^2 + 2x + 1 的导数"
    print(f"\n发送测试消息: '{question}'")
    print("-" * 40)
    print("输出: ", end="", flush=True)

    start_time = time.time()
    char_count = 0
    last_update = start_time

    async for chunk in agent.stream(question):
        if chunk:
            print(chunk, end="", flush=True)
            char_count += 1

            now = time.time()
            if now - last_update >= 1.5:
                elapsed = now - start_time
                speed = char_count / elapsed if elapsed > 0 else 0
                print(f"\n[进度] {char_count} 字, {elapsed:.1f}秒, {speed:.1f} 字/秒", end="", flush=True)
                last_update = now

    elapsed = time.time() - start_time
    print(f"\n\n[完成] 总计 {char_count} 字, 耗时 {elapsed:.1f}秒")


async def test_sse_format():
    """测试 SSE 格式输出。"""
    print("\n" + "=" * 60)
    print("SSE 格式测试")
    print("=" * 60)

    from main import stream_chat_response

    print("\n测试 SSE 格式:")
    print("-" * 40)

    count = 0
    async for sse_line in stream_chat_response("你好", "test_session"):
        if sse_line.startswith("data: "):
            count += 1
            if count <= 5:
                print(sse_line.strip())
            elif count == 6:
                print("... (更多输出)")
        if count > 20:
            break

    print(f"\n[完成] 发送了 {count} 条 SSE 消息")


async def main():
    print("\n" + "=" * 60)
    print("Math AI Assistant 流式输出测试")
    print("=" * 60)

    try:
        # 测试 1: 基础聊天流式输出
        await test_streaming_chat()

        # 测试 2: 数学问题流式输出
        await test_streaming_math()

        # 测试 3: SSE 格式
        await test_sse_format()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

    except Exception as e:
        import traceback
        print(f"\n[错误] {type(e).__name__}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
