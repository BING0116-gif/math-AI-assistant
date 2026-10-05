"""流式取消控制（路线图 4.5）。

进程级注册表：stream_id → 取消事件。用户主动停止（DELETE /api/chat/stream/{id}）
设置事件；流式生成器在 chunk 间隙轮询并优雅收尾（status=user_cancelled，
已产出内容保留，半截结果不进记忆/错题本）。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_EVENTS: dict[str, asyncio.Event] = {}


def register_stream(stream_id: str) -> asyncio.Event:
    event = _EVENTS.get(stream_id)
    if event is None:
        event = asyncio.Event()
        _EVENTS[stream_id] = event
    return event


def unregister_stream(stream_id: str) -> None:
    _EVENTS.pop(stream_id, None)


def cancel_stream(stream_id: str) -> bool:
    """Request cancellation; idempotent. Returns False when the stream is unknown."""
    event = _EVENTS.get(stream_id)
    if event is None:
        return False
    event.set()
    return True


def is_cancelled(stream_id: str) -> bool:
    event = _EVENTS.get(stream_id)
    return bool(event is not None and event.is_set())
