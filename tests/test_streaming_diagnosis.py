"""
SSE 流式输出诊断工具

用法:
    python tests/test_streaming_diagnosis.py

功能:
    1. 直接调用 /api/chat 接口
    2. 实时打印每个收到的 chunk 及时间戳
    3. 统计总 chunk 数、总耗时、平均间隔
    4. 判断是"真流式"还是"一次性返回"
"""

import asyncio
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def diagnose_sse():
    """直接测试后端 SSE 输出，不经过前端。"""

    import httpx

    url = "http://localhost:8000/api/chat"
    payload = {"message": "1+1等于几？", "session_id": "diagnose-test"}

    print("=" * 60)
    print("  SSE 流式输出诊断")
    print("=" * 60)
    print(f"  URL: {url}")
    print(f"  Payload: {payload}")
    print("-" * 60)

    start = time.time()
    chunk_count = 0
    first_chunk_time = None
    last_chunk_time = None
    intervals = []
    all_contents = []

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                status = response.status_code
                content_type = response.headers.get("content-type", "")
                print(f"\n[响应状态] HTTP {status} | Content-Type: {content_type}\n")

                if status != 200:
                    body = await response.aread()
                    print(f"[错误] 非200状态: {body.decode()[:500]}")
                    return

                buffer = ""
                async for raw_bytes in response.aiter_bytes():
                    text = raw_bytes.decode("utf-8", errors="replace")
                    buffer += text

                    while "\n\n" in buffer:
                        line, buffer = buffer.split("\n\n", 1)
                        line = line.strip()

                        if not line or not line.startswith("data: "):
                            continue

                        now = time.time()
                        data_str = line[6:]

                        if data_str.strip() == "" or data_str == "[DONE]":
                            continue

                        try:
                            parsed = json.loads(data_str)
                        except json.JSONDecodeError:
                            print(f"  [!] JSON解析失败: {data_str[:100]}")
                            continue

                        msg_type = parsed.get("type", "?")
                        content = parsed.get("content", "")

                        chunk_count += 1
                        elapsed_ms = (now - start) * 1000

                        if first_chunk_time is None:
                            first_chunk_time = now
                            ttfb_ms = (now - start) * 1000
                            print(f"  [首字节] TTFB = {ttfb_ms:.0f}ms")
                            print()
                            print(f"  {'#':>4} | {'类型':>6} | {'距首字节':>8} | {'内容预览'}")
                            print(f"  {'-'*4}-+-{'-'*6}-+-{'-'*8}-+{'-'*30}")

                        if last_chunk_time is not None:
                            interval_ms = (now - last_chunk_time) * 1000
                            intervals.append(interval_ms)

                        last_chunk_time = now
                        from_first = (now - first_chunk_time) * 1000

                        preview = repr(content[:40]) if len(content) > 40 else repr(content)
                        print(f"  {chunk_count:>4} | {msg_type:>6} | {from_first:>7.0f}ms | {preview}")

                        if msg_type == "content" and content:
                            all_contents.append(content)

                        if msg_type == "done":
                            print(f"\n  [完成] 收到 done 信号")
                            break

                total_ms = (time.time() - start) * 1000

    except httpx.ConnectError:
        print("\n[错误] 无法连接到 localhost:8000")
        print("       请确保服务已启动: python main.py 或 uvicorn main:app --reload")
        return
    except Exception as e:
        print(f"\n[异常] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("=" * 60)
    print("  诊断结果")
    print("=" * 60)

    full_text = "".join(all_contents)
    print(f"  总耗时:          {total_ms:.0f}ms")
    print(f"  首字节时间(TTFB): {(first_chunk_time - start) * 1000:.0f}ms" if first_chunk_time else "  首字节时间: N/A (未收到任何chunk)")
    print(f"  总 chunk 数:     {chunk_count}")
    print(f"  内容总长度:      {len(full_text)} 字符")
    print(f"  完整回复:        '{full_text[:100]}{'...' if len(full_text)>100 else ''}'")

    if intervals:
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)
        print(f"  chunk 平均间隔:   {avg_interval:.0f}ms")
        print(f"  chunk 最小间隔:   {min_interval:.0f}ms")
        print(f"  chunk 最大间隔:   {max_interval:.0f}ms")

    print()
    print("--- 判定 ---")

    if chunk_count <= 1:
        print("  ❌ 问题定位: 后端只返回了 1 个或 0 个 chunk")
        print("     → 后端不是流式输出，而是一次性返回全部内容")
        print("     → 可能原因:")
        print("       a) agent.astream() 的 stream_mode='values' 导致整个回复作为单个事件返回")
        print("       b) LLM 响应太快，所有 token 在一个事件中返回")
        print("       c) 某层代码缓冲了输出")
    elif chunk_count >= 5 and (sum(intervals)/len(intervals)) < 50:
        print("  ✅ 正常流式: 多个 chunk，间隔短 (<50ms)，是真正的逐token/逐片段流式")
    elif chunk_count >= 3 and (sum(intervals)/len(intervals)) < 200:
        print("  ⚠️ 半流式: 有多个 chunk 但间隔较大，可能是逐句而非逐字")
        print("     → 前端 processTyping() 会做逐字动画，所以用户仍能看到打字效果")
    else:
        print(f"  ⚠️ 异常模式: chunk_count={chunk_count}, 请检查上方详细日志")

    if chunk_count <= 1:
        print()
        print("--- 建议 ---")
        print("  如果后端确实只返回1个chunk，问题在 langchain_react.py 的 stream_mode='values'")
        print("  这个模式下 LangChain 在每个节点完成后才发送完整状态，对于简单问题可能只有1次发送")


if __name__ == "__main__":
    asyncio.run(diagnose_sse())
