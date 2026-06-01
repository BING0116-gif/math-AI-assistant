"""
A03 记忆持久化专项测试
运行: pytest tests/test_memory_persistence.py -v
"""

import asyncio
import time
import pytest
from app.services.event_buffer import EnhancedEventBuffer, BufferedEvent
from app.services.memory import (
    LongTermMemory, EventClassification, ShortTermMemory, MemoryItem
)
from agent_core.memory_persistence import MemoryPersistenceFacade, UserProfile


class TestEventBuffer:
    @pytest.mark.asyncio
    async def test_add_below_threshold(self):
        buf = EnhancedEventBuffer(batch_size=5)
        for i in range(3):
            await buf.add(BufferedEvent("u1", "q", f"test {i}", "代数", {}))
        assert buf.buffer_size == 3

    @pytest.mark.asyncio
    async def test_flush_on_batch_full(self):
        buf = EnhancedEventBuffer(batch_size=2)
        await buf.add(BufferedEvent("u1", "q", "test 1", "代数", {}))
        await buf.add(BufferedEvent("u1", "q", "test 2", "代数", {}))
        await asyncio.sleep(0.2)
        assert buf.buffer_size == 0

    @pytest.mark.asyncio
    async def test_dedup_same_content(self):
        buf = EnhancedEventBuffer(batch_size=10)
        assert await buf.add(BufferedEvent("u1", "q", "same", "代数", {}))
        assert not await buf.add(BufferedEvent("u1", "q", "same", "代数", {}))
        assert buf.buffer_size == 1

    @pytest.mark.asyncio
    async def test_dedup_different_user(self):
        buf = EnhancedEventBuffer(batch_size=10)
        assert await buf.add(BufferedEvent("u1", "q", "same", "代数", {}))
        assert await buf.add(BufferedEvent("u2", "q", "same", "代数", {}))
        assert buf.buffer_size == 2

    @pytest.mark.asyncio
    async def test_force_flush(self):
        buf = EnhancedEventBuffer(batch_size=100)
        for i in range(5):
            await buf.add(BufferedEvent("u1", "q", f"test {i}", "代数", {}))
        assert buf.buffer_size == 5
        count = await buf.force_flush()
        assert count == 5
        assert buf.buffer_size == 0

    @pytest.mark.asyncio
    async def test_buffer_max_size(self):
        buf = EnhancedEventBuffer(max_buffer_size=3, batch_size=100)
        for i in range(5):
            await buf.add(BufferedEvent("u1", "q", f"test {i}", "代数", {}))
        assert buf.buffer_size <= 3


class TestEventClassification:
    def test_fallback_limits(self):
        from app.data.database import get_db_session
        ltm = LongTermMemory(get_db_session)

        result = ltm._classify_fallback({
            "question_content": "求积分 x dx",
            "is_correct": True,
        })
        assert result.category == "积分"

        result = ltm._classify_fallback({
            "question_content": "求导数 dy/dx",
            "is_correct": False,
        })
        assert result.category == "导数"


class TestMemoryPersistenceFacade:
    @pytest.mark.asyncio
    async def test_profile_type(self):
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile("test_user")
        assert isinstance(profile, UserProfile)

    @pytest.mark.asyncio
    async def test_profile_dict_has_required_fields(self):
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile("test_user")
        d = profile.to_dict()
        for field in [
            "total_questions", "correct_rate", "weak_points",
            "strong_points", "skills", "error_patterns",
        ]:
            assert field in d, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_compact_json_under_limit(self):
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile("test_user")
        compact = profile.to_compact_json(max_length=1000)
        assert len(compact) <= 1000

    def test_intent_persistence_map(self):
        facade = MemoryPersistenceFacade()
        assert facade.should_persist("problem_solving") == True
        assert facade.should_persist("casual_chat") == False


class TestPerformance:
    @pytest.mark.asyncio
    async def test_buffer_add_latency(self):
        buf = EnhancedEventBuffer(batch_size=1000)
        latencies = []
        for i in range(100):
            start = time.perf_counter()
            await buf.add(BufferedEvent("u1", "q", f"perf {i}", "代数", {}))
            latencies.append(time.perf_counter() - start)

        avg = sum(latencies) / len(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert avg < 0.01, f"avg latency {avg:.4f}s > 10ms"
        assert p99 < 0.05, f"P99 latency {p99:.4f}s > 50ms"