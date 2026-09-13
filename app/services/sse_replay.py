"""Short-lived, owner-scoped SSE replay buffer for recoverable chat streams."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _Stream:
    user_id: str
    session_id: str
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    next_seq: int = 0
    events: deque[tuple[int, str]] = field(default_factory=lambda: deque(maxlen=4096))
    closed: bool = False
    task: asyncio.Task | None = None


class SSEReplayBuffer:
    """Process-local five-minute ring buffer; entries are never shared between users."""
    ttl_seconds = 300

    def __init__(self) -> None:
        self._streams: dict[str, _Stream] = {}
        self._lock = asyncio.Lock()

    async def create(self, user_id: str, session_id: str) -> str:
        async with self._lock:
            self._prune()
            stream_id = str(uuid.uuid4())
            self._streams[stream_id] = _Stream(user_id=user_id, session_id=session_id)
            return stream_id

    async def start(self, source, user_id: str, session_id: str) -> str:
        """Run the producer independently from any one HTTP connection."""
        stream_id = await self.create(user_id, session_id)
        stream = self._streams[stream_id]
        stream.task = asyncio.create_task(
            self._produce(source, stream_id, user_id, session_id),
            name=f"sse-producer:{stream_id}",
        )
        return stream_id

    async def append(self, stream_id: str, user_id: str, session_id: str, payload: str) -> tuple[int, str]:
        async with self._lock:
            stream = self._owned(stream_id, user_id, session_id)
            seq = stream.next_seq
            stream.next_seq += 1
            stream.updated_at = time.monotonic()
            encoded = f"id: {seq}\n{payload}"
            stream.events.append((seq, encoded))
            return seq, encoded

    async def replay(self, stream_id: str, user_id: str, session_id: str, after_seq: int) -> list[str]:
        async with self._lock:
            stream = self._owned(stream_id, user_id, session_id)
            return [payload for seq, payload in stream.events if seq > after_seq]

    async def subscribe(self, stream_id: str, user_id: str, session_id: str, after_seq: int = -1):
        """Yield buffered and future events once, continuing after disconnects."""
        cursor = after_seq
        while True:
            async with self._lock:
                stream = self._owned(stream_id, user_id, session_id)
                pending = [(seq, payload) for seq, payload in stream.events if seq > cursor]
                closed = stream.closed
            for seq, payload in pending:
                cursor = seq
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
