from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BufferedEvent:
    """缓冲区中的事件"""
    user_id: str
    event_type: str
    question_content: str
    category: str
    data: Dict[str, Any]
    content_hash: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(
                f"{self.user_id}:{self.event_type}:{self.question_content[:100]}".encode()
            ).hexdigest()


class EnhancedEventBuffer:
    """
    增强事件缓冲器。

    特性:
    - 事件先入内存 deque (maxlen=200)
    - 满足以下任一条件时批量刷新:
      1. 缓冲区 ≥ 50 条
      2. 距上次刷新 ≥ 30 秒
      3. 会话结束（外部调用 force_flush）
    - 去重: 5 分钟窗口内 (user_id, event_type, content_hash) 相同则跳过
    - 异步刷新: asyncio.create_task，不阻塞主流程
    """

    def __init__(
        self,
        max_buffer_size: int = 200,
        batch_size: int = 50,
        flush_interval_seconds: int = 30,
        dedup_window_seconds: int = 300,
    ):
        self.max_buffer_size = max_buffer_size
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self.dedup_window_seconds = dedup_window_seconds

        self._buffer: deque[BufferedEvent] = deque(maxlen=max_buffer_size)
        self._last_flush_time = time.time()
        self._seen_hashes: Dict[str, float] = {}
        self._flush_lock = asyncio.Lock()
        self._on_flush_callbacks: List[callable] = []

    async def add(self, event: BufferedEvent) -> bool:
        now = time.time()
        if event.content_hash in self._seen_hashes:
            last_seen = self._seen_hashes[event.content_hash]
            if (now - last_seen) < self.dedup_window_seconds:
                logger.debug(f"事件去重: hash={event.content_hash[:8]}")
                return False

        self._seen_hashes[event.content_hash] = now
        self._buffer.append(event)

        if len(self._buffer) >= self.batch_size:
            asyncio.create_task(self._flush())
        elif (now - self._last_flush_time) >= self.flush_interval_seconds:
            asyncio.create_task(self._flush())

        self._cleanup_hashes(now)

        return True

    async def force_flush(self) -> int:
        return await self._flush()

    def on_flush(self, callback: callable) -> None:
        self._on_flush_callbacks.append(callback)

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "buffer_size": len(self._buffer),
            "last_flush_time": self._last_flush_time,
            "seen_hashes_count": len(self._seen_hashes),
        }

    async def _flush(self) -> int:
        async with self._flush_lock:
            if not self._buffer:
                return 0

            events = list(self._buffer)
            self._buffer.clear()
            self._last_flush_time = time.time()

            logger.info(f"刷新 {len(events)} 条事件到数据库")

            for callback in self._on_flush_callbacks:
                try:
                    await callback(events)
                except Exception as e:
                    logger.warning(f"刷新回调异常: {e}")

            return len(events)

    def _cleanup_hashes(self, now: float):
        expired = [
            h
            for h, t in self._seen_hashes.items()
            if (now - t) >= self.dedup_window_seconds
        ]
        for h in expired:
            del self._seen_hashes[h]