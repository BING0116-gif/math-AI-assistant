"""Short-lived, owner-scoped SSE replay buffer for recoverable chat streams."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field


def _capacity_setting(name: str, fallback):
    try:
        from app.config.settings import settings

        return getattr(settings, name)
    except Exception:
        return fallback


RESET_EVENT = 'event: reset\ndata: {"reason": "seq_hole"}\n\n'


@dataclass
class _Stream:
    user_id: str
    session_id: str
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    next_seq: int = 0
    events: deque[tuple[int, str]] = field(default_factory=deque)
    closed: bool = False
    task: asyncio.Task | None = None
    # 4.6.3 容量治理：淘汰最老事件后记录保留边界，恢复时据此发 reset 指令
    min_retained_seq: int = 0
    evicted: bool = False
    retained_bytes: int = 0


class SSEReplayBuffer:
    """Process-local short-lived ring buffer; entries are never shared between users."""

    ttl_seconds = 300

    def __init__(
        self,
        *,
        max_events: int | None = None,
        max_bytes: int | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self._streams: dict[str, _Stream] = {}
        self._lock = asyncio.Lock()
        self.max_events = int(max_events if max_events is not None else (_capacity_setting("SSE_BUFFER_MAX_EVENTS", 2000) or 2000))
        self.max_bytes = int(max_bytes if max_bytes is not None else (_capacity_setting("SSE_BUFFER_MAX_BYTES", 2 * 1024 * 1024) or 2 * 1024 * 1024))
        self.ttl_seconds = float(ttl_seconds if ttl_seconds is not None else (_capacity_setting("SSE_STREAM_TTL_SECONDS", 300) or 300))

    async def create(self, user_id: str, session_id: str) -> str:
        async with self._lock:
            self._prune()
            stream_id = str(uuid.uuid4())
            self._streams[stream_id] = _Stream(user_id=user_id, session_id=session_id)
            return stream_id

    async def start(self, source, user_id: str, session_id: str, stream_id: str | None = None) -> str:
        """Run the producer independently from any one HTTP connection.

        允许传入预创建的 stream_id（取消端点需要在响应返回前就拿到同一 id）。
        """
        stream_id = stream_id or await self.create(user_id, session_id)
        stream = self._streams.get(stream_id)
        if stream is None or stream.user_id != user_id or stream.session_id != session_id:
            raise LookupError("SSE stream not found")
        stream.task = asyncio.create_task(
            self._produce(source, stream_id, user_id, session_id),
            name=f"sse-producer:{stream_id}",
        )
        return stream_id

    def owns_stream(self, stream_id: str, user_id: str) -> bool:
        """Ownership check for the cancel endpoint (no session context available)."""
        self._prune()
        stream = self._streams.get(stream_id)
        return stream is not None and stream.user_id == user_id

    async def append(self, stream_id: str, user_id: str, session_id: str, payload: str) -> tuple[int, str]:
        async with self._lock:
            stream = self._owned(stream_id, user_id, session_id)
            seq = stream.next_seq
            stream.next_seq += 1
            stream.updated_at = time.monotonic()
            encoded = f"id: {seq}\n{payload}"
            stream.events.append((seq, encoded))
            stream.retained_bytes += len(encoded)
            # 4.6.3：事件数/字节超限淘汰最老事件，保留边界前移（seq_hole 可判定）。
            while stream.events and (len(stream.events) > self.max_events or stream.retained_bytes > self.max_bytes):
                old_seq, old_payload = stream.events.popleft()
                stream.retained_bytes -= len(old_payload)
                stream.min_retained_seq = old_seq + 1
                stream.evicted = True
            return seq, encoded

    def _replay_payloads(self, stream: _Stream, after_seq: int) -> list[str]:
        """Build replay payloads; a detected seq hole yields a reset + full retained replay."""
        if stream.evicted and after_seq < stream.min_retained_seq - 1:
            return [RESET_EVENT] + [payload for _, payload in stream.events]
        return [payload for seq, payload in stream.events if seq > after_seq]

    async def replay(self, stream_id: str, user_id: str, session_id: str, after_seq: int) -> list[str]:
        async with self._lock:
            stream = self._owned(stream_id, user_id, session_id)
            return self._replay_payloads(stream, after_seq)

    async def subscribe(self, stream_id: str, user_id: str, session_id: str, after_seq: int = -1):
        """Yield buffered and future events once, continuing after disconnects."""
        cursor = after_seq
        hole_announced = False
        while True:
            async with self._lock:
                stream = self._owned(stream_id, user_id, session_id)
                if stream.evicted and not hole_announced and cursor < stream.min_retained_seq - 1:
                    # seq_hole：告知客户端历史不完整，随后整段重放保留区。
                    hole_announced = True
                    pending = [RESET_EVENT] + [payload for _, payload in stream.events]
                    cursor = stream.next_seq - 1
                else:
                    pending = [payload for seq, payload in stream.events if seq > cursor]
                    if pending:
                        cursor = stream.events[-1][0]
                closed = stream.closed
            for payload in pending:
                yield payload
            if closed:
                return
            await asyncio.sleep(0.05)

    async def _produce(self, source, stream_id: str, user_id: str, session_id: str) -> None:
        try:
            await self.append(
                stream_id,
                user_id,
                session_id,
                f'event: stream\ndata: {{"stream_id": "{stream_id}"}}\n\n',
            )
            async for event in source:
                await self.append(stream_id, user_id, session_id, event)
        finally:
            async with self._lock:
                stream = self._streams.get(stream_id)
                if stream:
                    stream.closed = True

    def _owned(self, stream_id: str, user_id: str, session_id: str) -> _Stream:
        self._prune()
        stream = self._streams.get(stream_id)
        if not stream or stream.user_id != user_id or stream.session_id != session_id:
            raise LookupError("SSE stream not found")
        return stream

    def _prune(self) -> None:
        now = time.monotonic()
        for stream_id in [key for key, item in self._streams.items() if item.closed and now - item.updated_at > self.ttl_seconds]:
            self._streams.pop(stream_id, None)


_buffer = SSEReplayBuffer()


def get_sse_replay_buffer() -> SSEReplayBuffer:
    return _buffer
