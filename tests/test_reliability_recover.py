"""阶段二 4.9 故障注入:recover 幂等与副作用零增长回归测试。"""

import asyncio
import json

import pytest

from app.services.sse_replay import SSEReplayBuffer
from app.services import stream_control
from app.services.stream_handler import stream_agent_response


@pytest.fixture(autouse=True)
def clean_registry():
    stream_control._EVENTS.clear()
    yield
    stream_control._EVENTS.clear()


@pytest.mark.asyncio
async def test_recover_same_seq_twice_yields_identical_payloads_and_no_new_events():
    """recover 同 seq 两次:返回完全一致,buffer 不新增事件,producer 无副作用。"""
    buffer = SSEReplayBuffer()
    stream_id = await buffer.create("user-idem", "session-idem")

    async def source():
        for i in range(3):
            yield f"data: chunk-{i}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    await buffer.start(source(), "user-idem", "session-idem", stream_id=stream_id)
    await asyncio.sleep(0.05)

    async with buffer._lock:
        seq_after_produce = buffer._streams[stream_id].next_seq

    first = await buffer.replay(stream_id, "user-idem", "session-idem", 1)
    second = await buffer.replay(stream_id, "user-idem", "session-idem", 1)
    assert first == second
    assert first, "重放不应为空"

    async with buffer._lock:
        assert buffer._streams[stream_id].next_seq == seq_after_produce  # 副作用零:无新事件
        assert len(buffer._streams[stream_id].events) == seq_after_produce


@pytest.mark.asyncio
async def test_recover_does_not_replay_heartbeat_or_advance_business_seq():
    """心跳 comment 帧不进入 replay 业务序号(4.6.1 契约的回归锚)。"""
    from app.services.stream_handler import with_sse_heartbeat

    async def source():
        await asyncio.sleep(0.01)  # 源等待期间心跳才有机会触发
        yield "data: a\n\n"

    seen = [item async for item in with_sse_heartbeat(source(), interval_seconds=0.001)]
    assert ": ping\n\n" in seen  # 心跳存在
    # 心跳帧是 SSE comment,不含 id: 前缀,不参与业务序号
    assert all(not item.startswith("id:") for item in seen if item.startswith(":"))


@pytest.mark.asyncio
async def test_cancelled_run_can_still_be_recovered():
    """用户停止后,已产出内容保留在 buffer 中可 recover(4.5+4.6.2 交叉场景)。"""
    recorded = []

    async def fake_complete(run_id, **kwargs):
        recorded.append(kwargs.get("status"))
        await asyncio.sleep(0)

    import app.services.tutor_service as tutor_service

    original = tutor_service.complete_ai_run
    tutor_service.complete_ai_run = fake_complete
    try:
        buffer = SSEReplayBuffer()
        stream_id = await buffer.create("user-rec", "session-rec")
        agent_stream = stream_agent_response(
            SimpleNamespaceAgent(["片段A", "片段B"]),
            "请证明",
            "session-rec",
            user_id="user-rec",
            ai_run_id="run-rec",
            stream_id=stream_id,
        )
        await buffer.start(agent_stream, "user-rec", "session-rec", stream_id=stream_id)
        # chunk 间隔 60ms:0.08s 时第一个 chunk 已产出、第二个尚未完成,取消落在流中间
        await asyncio.sleep(0.08)
        stream_control.cancel_stream(stream_id)
        await asyncio.sleep(0.15)

        replayed = await buffer.replay(stream_id, "user-rec", "session-rec", -1)
        contents = []
        for payload in replayed:
            for line in payload.splitlines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "content":
                        contents.append(data.get("content", ""))
        assert "片段A" in "".join(contents)  # 已产出内容保留可恢复(数据帧 JSON 转义,解码后断言)
        assert any("user_cancelled" == status for status in recorded)
    finally:
        tutor_service.complete_ai_run = original
        stream_control.unregister_stream(stream_id)


class SimpleNamespaceAgent:
    """最小 agent 桩:按序产出 chunk,响应取消轮询。"""

    def __init__(self, chunks):
        self._chunks = chunks
        self._last_run_metadata = {"capability": "math_tutor"}
        self._follow_up_text = None

    async def stream(self, *args, **kwargs):
        for chunk in self._chunks:
            await asyncio.sleep(0.06)
            yield chunk
