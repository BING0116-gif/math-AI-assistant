"""
异步记忆写入任务。

提供线程池 + 异步队列的写入能力，支持：
- 单条异步写入
- 批量聚合写入
- 单用户串行化（避免并发重复）
- 速率限制
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.services.memory_store import MemoryStore, get_memory_store

logger = logging.getLogger(__name__)


class AsyncMemoryWriter:
    """异步记忆写入器，管理写入队列和速率限制。"""

    def __init__(self):
        self._store: Optional[MemoryStore] = None
        self._pending_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._last_write_time: Dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()
        self._batch_size = settings.MEMORY_BATCH_WRITE_SIZE
        self._rate_limit = settings.MEMORY_USER_RATE_LIMIT  # 每秒最多写入数

    async def _get_store(self) -> MemoryStore:
        if self._store is None:
            self._store = get_memory_store()
        return self._store

    async def write_error_memory(
        self,
        user_id: str,
        question_id: str,
        question_content: str,
        high_category: str = "",
        category: str = "",
        knowledge_points: Optional[List[str]] = None,
        difficulty: int = 3,
        user_answer: str = "",
        correct_answer: str = "",
        error_type: str = "",
    ) -> Optional[int]:
        """异步写入错题记忆（含速率控制）。"""
        if not await self._check_rate_limit(user_id):
            logger.warning(f"[异步写入] 用户 {user_id} 写入速率超限，加入批量队列")
            self._pending_batches[user_id].append({
                "type": "error",
                "question_id": question_id,
                "question_content": question_content,
                "high_category": high_category,
                "category": category,
                "knowledge_points": knowledge_points,
                "difficulty": difficulty,
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "error_type": error_type,
            })
            return None

        store = await self._get_store()
        return await store.create_error_memory(
            user_id=user_id,
            question_id=question_id,
            question_content=question_content,
            high_category=high_category,
            category=category,
            knowledge_points=knowledge_points,
            difficulty=difficulty,
            user_answer=user_answer,
            correct_answer=correct_answer,
            error_type=error_type,
        )

    async def write_conversation_memory(
        self,
        user_id: str,
        content: str,
        high_category: str = "",
        category: str = "",
        importance: float = 0.6,
        tags: Optional[List[str]] = None,
    ) -> Optional[int]:
        """异步写入对话记忆。"""
        store = await self._get_store()
        return await store.create_conversation_memory(
            user_id=user_id,
            content=content,
            high_category=high_category,
            category=category,
            importance=importance,
            tags=tags,
        )

    async def write_milestone_memory(
        self,
        user_id: str,
        milestone_type: str,
        description: str,
        high_category: str = "",
        category: str = "",
    ) -> Optional[int]:
        """异步写入里程碑记忆。"""
        store = await self._get_store()
        return await store.create_milestone_memory(
            user_id=user_id,
            milestone_type=milestone_type,
            description=description,
            high_category=high_category,
            category=category,
        )

    async def write_profile_memory(
        self,
        user_id: str,
        summary_text: str,
        full_profile_json: str,
        high_category: str = "",
        category: str = "",
    ) -> Optional[int]:
        """异步写入画像记忆。"""
        store = await self._get_store()
        return await store.create_profile_memory(
            user_id=user_id,
            summary_text=summary_text,
            full_profile_json=full_profile_json,
            high_category=high_category,
            category=category,
        )

    async def flush_pending_batch(self, user_id: str) -> int:
        """刷入指定用户的待处理批量队列。"""
        async with self._lock:
            pending = self._pending_batches.pop(user_id, [])
            if not pending:
                return 0

        store = await self._get_store()
        written_count = 0

        for item in pending:
            if item.get("type") == "error":
                result = await store.create_error_memory(
                    user_id=user_id,
                    question_id=item.get("question_id", ""),
                    question_content=item.get("question_content", ""),
                    high_category=item.get("high_category", ""),
                    category=item.get("category", ""),
                    knowledge_points=item.get("knowledge_points", []),
                    difficulty=item.get("difficulty", 3),
                    user_answer=item.get("user_answer", ""),
                    correct_answer=item.get("correct_answer", ""),
                    error_type=item.get("error_type", ""),
                )
                if result is not None:
                    written_count += 1

        if written_count > 0:
            logger.info(f"[异步写入] 批量刷入完成: user={user_id}, count={written_count}")

        return written_count

    async def flush_all_pending(self) -> int:
        """刷入所有用户的待处理批量队列。"""
        async with self._lock:
            user_ids = list(self._pending_batches.keys())

        total = 0
        for uid in user_ids:
            total += await self.flush_pending_batch(uid)

        return total

    async def _check_rate_limit(self, user_id: str) -> bool:
        """检查用户写入速率限制。"""
        now = time.time()
        last = self._last_write_time.get(user_id, 0)
        if now - last < 1.0 / max(self._rate_limit, 1):
            return False
        self._last_write_time[user_id] = now
        return True


# 全局单例
_async_writer_instance: Optional[AsyncMemoryWriter] = None


def get_async_memory_writer() -> AsyncMemoryWriter:
    global _async_writer_instance
    if _async_writer_instance is None:
        _async_writer_instance = AsyncMemoryWriter()
    return _async_writer_instance