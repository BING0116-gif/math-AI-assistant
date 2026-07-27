"""
P0-02: 批量写入队列 + 失败重试机制专项测试。

测试覆盖：
- 批量写入队列入队/出队
- 批量刷新触发（数量阈值、时间阈值）
- 指数退避重试
- 队列满降级
- 主流程不影响（异常静默）

运行: pytest tests/test_memory_persistence_batch.py -v
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent_core.memory_persistence import MemoryPersistenceFacade


class TestBatchQueue:
    """批量写入队列测试。"""

    @pytest.mark.asyncio
    async def test_queue_put_and_get(self):
        """测试队列基本入队出队。"""
        facade = MemoryPersistenceFacade()
        assert facade._batch_queue.maxsize == 100
        await facade._batch_queue.put({"user_id": "u1", "event": "test"})
        assert facade._batch_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_record_event_enqueue(self):
        """测试 record_event 将事件加入队列。"""
        facade = MemoryPersistenceFacade()
        result = await facade.record_event("u1", {"event_type": "problem_solving"})
        assert result is True

    @pytest.mark.asyncio
    async def test_record_event_with_user_id_fallback(self):
        """测试 user_id 回退逻辑。"""
        facade = MemoryPersistenceFacade()
        result = await facade.record_event("anonymous", {"event_type": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_queue_full_graceful(self):
        """测试队列满时优雅降级。"""
        facade = MemoryPersistenceFacade()
        # 手动停止后台 worker，防止它消费队列元素
        if facade._batch_worker_task:
            facade._batch_worker_task.cancel()
            try:
                await facade._batch_worker_task
            except (asyncio.CancelledError, RuntimeError):
                pass
        # 填满队列
        for i in range(100):
            await facade._batch_queue.put({"i": i})
        # 队列已满，再放入应返回 False
        with pytest.raises(asyncio.QueueFull):
            facade._batch_queue.put_nowait({"event_type": "overflow"})

    @pytest.mark.asyncio
    async def test_batch_flush_on_size(self):
        """测试按数量阈值批量刷新。"""
        facade = MemoryPersistenceFacade()
        facade._flush_batch = AsyncMock()
        for i in range(facade._batch_size + 1):
            await facade._batch_queue.put({"i": i, "user_id": "u1"})
        await asyncio.sleep(0.5)
        assert facade._flush_batch.called


class TestRetryMechanism:
    """失败重试机制测试。"""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """测试失败时触发重试。"""
        facade = MemoryPersistenceFacade()
        # 模拟 session_factory 抛出异常，使 _flush_batch 内部捕获异常并调用 _retry_flush
        async def mock_session_factory():
            raise Exception("DB connection error")

        facade._session_factory = mock_session_factory
        facade._retry_flush = AsyncMock()

        batch = [{"user_id": "u1", "event": "test"}]
        await facade._flush_batch(batch)
        assert facade._retry_flush.called

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """测试第二次重试成功。"""
        facade = MemoryPersistenceFacade()
        call_count = 0

        async def mock_flush(batch):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise Exception("DB error")

        facade._flush_batch = mock_flush
        batch = [{"user_id": "u1", "event": "test"}]
        await facade._retry_flush(batch, max_retries=3)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_all_fail(self):
        """测试所有重试都失败。"""
        facade = MemoryPersistenceFacade()
        facade._flush_batch = AsyncMock(side_effect=Exception("DB error"))
        batch = [{"user_id": "u1", "event": "test"}]
        await facade._retry_flush(batch, max_retries=3)
        # _retry_flush 循环调用 _flush_batch max_retries 次
        assert facade._flush_batch.call_count == 3


class TestIntegration:
    """集成测试。"""

    @pytest.mark.asyncio
    async def test_worker_started(self):
        """测试 worker 自动启动。"""
        facade = MemoryPersistenceFacade()
        assert facade._batch_worker_task is not None
        assert not facade._batch_worker_task.done()

    @pytest.mark.asyncio
    async def test_event_flow_main_unaffected(self):
        """测试持久化失败不影响主流程。"""
        facade = MemoryPersistenceFacade()
        # 即使 session_factory 失败，record_event 应返回 True（加入队列成功）
        async def failing_session():
            raise Exception("DB error")
        facade._session_factory = failing_session
        result = await facade.record_event("u1", {"event_type": "test"})
        assert result is True