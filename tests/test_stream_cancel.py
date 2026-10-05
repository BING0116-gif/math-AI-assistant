"""阶段二 4.5 取消与中断回归测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.services import stream_control
from app.services.sse_replay import SSEReplayBuffer
from app.services.stream_handler import stream_agent_response


def make_agent(chunks):
    async def stream(*args, **kwargs):
        for chunk in chunks:
            await asyncio.sleep(0)
            yield chunk

    return SimpleNamespace(stream=stream, _last_run_metadata={"capability": "math_tutor"}, _follow_up_text=None)


@pytest.fixture(autouse=True)
def clean_registry():
    stream_control._EVENTS.clear()
    yield
    stream_control._EVENTS.clear()


@pytest.mark.asyncio
async def test_stream_control_register_cancel_is_idempotent():
    event = stream_control.register_stream("s-1")
    assert not event.is_set()

    assert stream_control.cancel_stream("s-1") is True
    assert stream_control.cancel_stream("s-1") is True  # 幂等
    assert stream_control.is_cancelled("s-1")
    assert stream_control.cancel_stream("unknown") is False

    stream_control.unregister_stream("s-1")
    assert stream_control.cancel_stream("s-1") is False


@pytest.mark.asyncio
async def test_user_cancel_yields_cancelled_event_and_records_run(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "app.services.tutor_service.complete_ai_run",
        lambda run_id, **kwargs: recorded.append((run_id, kwargs.get("status"))) or asyncio.sleep(0),
    )

    stream_control.register_stream("s-cancel")
    stream_control.cancel_stream("s-cancel")

    chunks = [
        chunk
        async for chunk in stream_agent_response(
            make_agent(["答案片段"]),
            "请证明",
            "session-cancel",
            user_id="user-cancel",
            ai_run_id="run-cancel",
            stream_id="s-cancel",
        )
    ]

    assert not any("答案片段" in chunk for chunk in chunks)  # 触顶前已取消，无内容外泄
    assert any('"type": "cancelled"' in chunk for chunk in chunks)
    assert chunks[-1].startswith("data:")
    assert ("run-cancel", "user_cancelled") in recorded
    stream_control.unregister_stream("s-cancel")


@pytest.mark.asyncio
async def test_user_cancel_keeps_already_streamed_content(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "app.services.tutor_service.complete_ai_run",
        lambda run_id, **kwargs: recorded.append((run_id, kwargs.get("status"))) or asyncio.sleep(0),
    )

    agent = make_agent(["第一段", "第二段"])

    async def consume_then_cancel():
        gen = stream_agent_response(
            agent, "请证明", "session-cancel2",
            user_id="user-cancel2", ai_run_id="run-cancel2", stream_id="s-cancel2",
        )
        first = await gen.__anext__()
        stream_control.cancel_stream("s-cancel2")
        rest = []
        async for item in gen:
            rest.append(item)
        return first, rest

    first, rest = await consume_then_cancel()
    assert '"type": "content"' in first  # 已产出内容保留
    assert any('"type": "cancelled"' in item for item in rest)
    assert ("run-cancel2", "user_cancelled") in recorded
    stream_control.unregister_stream("s-cancel2")


@pytest.mark.asyncio
async def test_client_disconnect_records_run_without_completing(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "app.services.tutor_service.complete_ai_run",
        lambda run_id, **kwargs: recorded.append((run_id, kwargs.get("status"))) or asyncio.sleep(0),
    )

    gen = stream_agent_response(
        make_agent(["片段一", "片段二"]),
        "请证明",
        "session-drop",
        user_id="user-drop",
        ai_run_id="run-drop",
    )
    await gen.__anext__()
    await gen.aclose()  # 模拟客户端断连引发的生成器关闭
    await asyncio.sleep(0)  # 让 create_task 的回写执行

    assert ("run-drop", "client_disconnected") in recorded


@pytest.mark.asyncio
async def test_replay_buffer_supports_preset_stream_id_and_ownership():
    buffer = SSEReplayBuffer()
    stream_id = await buffer.create("user-own", "session-own")

    async def source():
        yield "data: {\"type\": \"done\"}\n\n"

    returned = await buffer.start(source(), "user-own", "session-own", stream_id=stream_id)
    assert returned == stream_id
    assert buffer.owns_stream(stream_id, "user-own") is True
    assert buffer.owns_stream(stream_id, "user-other") is False
    assert buffer.owns_stream("missing", "user-own") is False
    await asyncio.sleep(0.05)  # producer 完成


@pytest.mark.asyncio
async def test_cancel_endpoint_is_owner_scoped_and_idempotent(monkeypatch):
    from app.api.chat_api import cancel_chat_stream
    from app.services.sse_replay import get_sse_replay_buffer

    buffer = get_sse_replay_buffer()
    stream_id = await buffer.create("user-a", "session-a")
    # 真实链路中 producer 首个 chunk 间隔即注册；测试直接注册以模拟已开播状态
    stream_control.register_stream(stream_id)

    owner_request = SimpleNamespace(state=SimpleNamespace(user_id="user-a"))
    other_request = SimpleNamespace(state=SimpleNamespace(user_id="user-b"))

    result = await cancel_chat_stream(stream_id, owner_request)
    assert result == {"code": 0, "data": {"stream_id": stream_id, "cancelled": True}}
    assert stream_control.is_cancelled(stream_id)
    # 幂等：重复调用仍然成功
    again = await cancel_chat_stream(stream_id, owner_request)
    assert again["data"]["cancelled"] is True

    with pytest.raises(Exception) as denied:
        await cancel_chat_stream(stream_id, other_request)
    assert getattr(denied.value, "status_code", None) == 404
    stream_control.unregister_stream(stream_id)
