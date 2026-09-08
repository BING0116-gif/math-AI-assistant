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


# 模块级初始化数据库
@pytest.fixture(scope="module", autouse=True)
def _setup_database():
    """初始化数据库（供事件幂等测试使用）。"""
    from app.data.database import init_db, close_db

    asyncio.run(init_db())
    yield
    asyncio.run(close_db())


def _drain_queue(facade):
    """取出队列中所有事件（worker 未启动时确定性消费）。"""
    batch = []
    while not facade._batch_queue.empty():
        batch.append(facade._batch_queue.get_nowait())
    return batch


class TestEventIdempotency:
    """record_event + EventIdempotency 原子去重测试。

    覆盖：
    - 相同 event_id 重复投递多次 → learning_records 只增加 1 条
    - EventIdempotency 表正确记录已处理事件
    - 不同 event_id → 各自独立写入
    """

    async def _enqueue(self, facade, user_id, event, event_id=None):
        """阻止 worker 懒启动，确定性入队（否则 worker 可能异步消费造成竞态）。"""
        with patch.object(
            facade, "_ensure_batch_worker_started", return_value=None
        ):
            return await facade.record_event(
                user_id, dict(event), event_id=event_id
            )

    async def _cleanup(self, user_id: str, event_ids):
        from app.data.database import get_db_session
        from app.data.models import LearningRecord, EventIdempotency, User
        from sqlalchemy import delete

        async with get_db_session() as db:
            await db.execute(
                delete(LearningRecord).where(LearningRecord.user_id == user_id)
            )
            for eid in event_ids:
                await db.execute(
                    delete(EventIdempotency).where(EventIdempotency.event_id == eid)
                )
            await db.commit()

    async def _ensure_users(self, user_ids):
        """learning_records.user_id 外键引用 users.id，需先创建测试用户。"""
        from app.data.database import get_db_session
        from app.data.models import User
        from sqlalchemy import select

        async with get_db_session() as db:
            for uid in user_ids:
                exists = (
                    await db.execute(select(User).where(User.id == uid))
                ).scalar_one_or_none()
                if exists is None:
                    db.add(
                        User(
                            id=uid,
                            username=f"test_{uid}",
                            email=f"{uid}@test.local",
                            password_hash="x",
                            role="student",
                        )
                    )
            await db.commit()

    async def _count_records(self, user_id: str) -> int:
        from app.data.database import get_db_session
        from app.data.models import LearningRecord
        from sqlalchemy import select, func

        async with get_db_session() as db:
            result = await db.execute(
                select(func.count(LearningRecord.id)).where(
                    LearningRecord.user_id == user_id
                )
            )
            return result.scalar() or 0

    @pytest.mark.asyncio
    async def test_same_event_id_only_inserts_once(self):
        """相同 event_id 重复投递 → 事实记录只增加 1 次。"""
        facade = MemoryPersistenceFacade()

        user_id = "idem_user_1"
        event_id = "evt-dup-001"
        await self._ensure_users([user_id])
        await self._cleanup(user_id, [event_id])

        event = {
            "event_type": "answer_correct",
            "question_content": "求极限 lim(x->0) sinx/x",
            "category": "极限",
            "is_correct": True,
            "difficulty": 3,
        }

        # 同一事件重复投递 3 次
        for _ in range(3):
            await self._enqueue(facade, user_id, event, event_id=event_id)

        batch = _drain_queue(facade)
        assert len(batch) == 3
        await facade._flush_batch(batch)

        # 事实只写入 1 条
        assert await self._count_records(user_id) == 1

        # EventIdempotency 表记录该事件
        from app.data.database import get_db_session
        from app.data.models import EventIdempotency
        from sqlalchemy import select

        async with get_db_session() as db:
            row = (
                await db.execute(
                    select(EventIdempotency).where(
                        EventIdempotency.event_id == event_id
                    )
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.status == "processed"

    @pytest.mark.asyncio
    async def test_distinct_event_ids_insert_separately(self):
        """不同 event_id → 各自独立写入事实。"""
        facade = MemoryPersistenceFacade()

        user_id = "idem_user_2"
        e1, e2 = "evt-distinct-001", "evt-distinct-002"
        await self._ensure_users([user_id])
        await self._cleanup(user_id, [e1, e2])

        base = {
            "event_type": "answer_correct",
            "question_content": "求导数 dy/dx",
            "category": "导数",
            "is_correct": True,
        }
        await self._enqueue(facade, user_id, base, event_id=e1)
        await self._enqueue(facade, user_id, base, event_id=e2)

        batch = _drain_queue(facade)
        await facade._flush_batch(batch)

        assert await self._count_records(user_id) == 2

    @pytest.mark.asyncio
    async def test_event_id_isolation_between_users(self):
        """A 的事件不影响 B：各自独立写入事实，user_id 正确隔离。

        注意：event_id 在 EventIdempotency 中全局唯一，调用方应生成
        全局稳定 ID（如 {user_id}:{稳定键}），避免跨用户碰撞。
        此处验证 A 的处理不会把事实写入 B。
        """
        facade = MemoryPersistenceFacade()

        user_a, user_b = "idem_user_a", "idem_user_b"
        await self._ensure_users([user_a, user_b])
        await self._cleanup(user_a, ["evt-cross-001"])
        await self._cleanup(user_b, ["evt-cross-002"])

        base = {
            "event_type": "answer_correct",
            "question_content": "求积分",
            "category": "积分",
            "is_correct": True,
        }
        await self._enqueue(facade, user_a, base, event_id="evt-cross-001")
        await self._enqueue(facade, user_b, base, event_id="evt-cross-002")

        batch = _drain_queue(facade)
        await facade._flush_batch(batch)

        # 各自只写入自己的事实，user_id 正确归属
        assert await self._count_records(user_a) == 1
        assert await self._count_records(user_b) == 1

        from app.data.database import get_db_session
        from app.data.models import LearningRecord
        from sqlalchemy import select

        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(LearningRecord.user_id).where(
                        LearningRecord.user_id.in_([user_a, user_b])
                    )
                )
            ).scalars().all()
            assert sorted(rows) == sorted([user_a, user_b])


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
        # 先通过 record_event 触发 worker 懒启动
        await facade.record_event("u1", {"event_type": "init"})
        facade._flush_batch = AsyncMock()
        for i in range(facade._batch_size):
            await facade._batch_queue.put({"i": i, "user_id": "u1"})
        # 等待 worker 处理队列
        await asyncio.sleep(1.0)
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
        """测试 worker 自动启动（懒加载）。"""
        facade = MemoryPersistenceFacade()
        # 首次 record_event 触发懒启动
        await facade.record_event("u1", {"event_type": "init"})
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