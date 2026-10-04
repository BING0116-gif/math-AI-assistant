"""阶段二 4.6.3 SSE replay buffer 容量治理回归测试。"""

import asyncio

import pytest

from app.services.sse_replay import RESET_EVENT, SSEReplayBuffer


def make_buffer(**kwargs) -> SSEReplayBuffer:
    return SSEReplayBuffer(**kwargs)


@pytest.mark.asyncio
async def test_event_cap_evicts_oldest_and_replay_detects_seq_hole():
    buffer = SSEReplayBuffer(max_events=3, max_bytes=10**9, ttl_seconds=300)
    stream_id = await buffer.create("user-cap", "session-cap")

    async def source():
        for i in range(5):
            yield f"data: event-{i}\n\n"

    await buffer.start(source(), "user-cap", "session-cap", stream_id=stream_id)
    await asyncio.sleep(0.05)

    # 客户端停在 seq 1，但 0-2 已被淘汰（producer 首帧 event:stream 占 seq 0）→ seq_hole
    replayed = await buffer.replay(stream_id, "user-cap", "session-cap", 1)
    assert replayed[0] == RESET_EVENT
    # 整段重放保留区（seq 3、4、5 = event-2/3/4）
    assert "id: 3" in replayed[1] and "event-2" in replayed[1]
    assert "id: 5" in replayed[3] and "event-4" in replayed[3]

    # 客户端已见过最后被淘汰事件（seq 2）→ 无 hole，正常增量
    normal = await buffer.replay(stream_id, "user-cap", "session-cap", 2)
    assert RESET_EVENT not in normal
    assert len(normal) == 3 and "event-4" in normal[-1]


@pytest.mark.asyncio
async def test_byte_cap_evicts_oldest():
    buffer = SSEReplayBuffer(max_events=10**6, max_bytes=120, ttl_seconds=300)
    stream_id = await buffer.create("user-bytes", "session-bytes")

    async def source():
        for i in range(6):
            yield f"data: payload-{i} {'x' * 40}\n\n"

    await buffer.start(source(), "user-bytes", "session-bytes", stream_id=stream_id)
    await asyncio.sleep(0.05)

    async with buffer._lock:
        stream = buffer._streams[stream_id]
        assert stream.evicted is True
        assert stream.retained_bytes <= buffer.max_bytes
        assert stream.min_retained_seq > 0


@pytest.mark.asyncio
async def test_subscribe_announces_hole_once_then_streams_live():
    buffer = SSEReplayBuffer(max_events=2, max_bytes=10**9, ttl_seconds=300)
    stream_id = await buffer.create("user-sub", "session-sub")

    async def source():
        for i in range(4):
            yield f"data: live-{i}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    await buffer.start(source(), "user-sub", "session-sub", stream_id=stream_id)
    await asyncio.sleep(0.1)

    chunks = [chunk async for chunk in buffer.subscribe(stream_id, "user-sub", "session-sub", 0)]
    assert chunks[0] == RESET_EVENT
    # 整段重放保留区（容量 2：live-3 与 done），历史 live-0..2 已淘汰不可见
    assert sum("live-" in chunk for chunk in chunks) == 1
    assert '"type": "done"' in chunks[-1]
    assert chunks.count(RESET_EVENT) == 1


@pytest.mark.asyncio
async def test_expired_closed_stream_is_pruned():
    buffer = SSEReplayBuffer(ttl_seconds=0.0)
    stream_id = await buffer.create("user-ttl", "session-ttl")

    async def source():
        yield "data: {\"type\": \"done\"}\n\n"

    await buffer.start(source(), "user-ttl", "session-ttl", stream_id=stream_id)
    await asyncio.sleep(0.05)  # producer 结束并关闭
    await asyncio.sleep(0.01)  # TTL=0，下一次 _owned/_prune 触发清理

    with pytest.raises(LookupError):
        await buffer.replay(stream_id, "user-ttl", "session-ttl", -1)


@pytest.mark.asyncio
async def test_no_eviction_keeps_classic_incremental_replay():
    buffer = SSEReplayBuffer(max_events=100, max_bytes=10**9, ttl_seconds=300)
    stream_id = await buffer.create("user-plain", "session-plain")

    async def source():
        for i in range(3):
            yield f"data: e-{i}\n\n"

    await buffer.start(source(), "user-plain", "session-plain", stream_id=stream_id)
    await asyncio.sleep(0.05)

    replayed = await buffer.replay(stream_id, "user-plain", "session-plain", 0)
    assert RESET_EVENT not in replayed
    assert [f"id: {seq}" in payload for seq, payload in zip((1, 2), replayed)] == [True, True]
