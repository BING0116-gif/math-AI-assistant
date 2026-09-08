# -*- coding: utf-8 -*-
"""
Step 0.5-B：ProfileSnapshot 统一画像入口专项测试。

覆盖（对应实施说明 §23 / §25 验收标准）：
1. Snapshot 接口：get_profile_snapshot / refresh_profile_snapshot / invalidate_profile_snapshot
2. Snapshot 幂等：同一事实数据连续 refresh 两次，业务画像完全一致
3. Profile rebuild：删除 user_profiles 快照 + 清缓存后重新 get，业务画像一致
4. Redis down 降级：Redis 不可用时 Snapshot / Agent / Recommendation 均正常
5. User isolation：user_A / user_B 在 DB / cache / snapshot / skill / event 全部隔离
6. SkillAggregator 幂等：重复读取 canonical UserKnowledgeState 结果一致
7. Event 幂等：相同 event_id 重复投递 → 事实记录只写入 1 次
8. PostgreSQL compatibility：源码中不再存在 MySQL/SQLite 专用 SQL（静态断言）

运行: pytest tests/test_profile_snapshot.py -v
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# 模块级：使用独立临时测试库，避免污染 data/math_ai.db
@pytest.fixture(scope="module", autouse=True)
def _setup_database():
    test_dir = tempfile.mkdtemp(prefix="profile_snapshot_test_")
    os.environ["ASYNC_DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{test_dir}/test_profile_snapshot.db"
    )
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


class ProfileTestBase:
    """公共工具：用户创建 / 数据清理 / 事件入队。"""

    async def _ensure_users(self, user_ids):
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
                            username=f"psn_{uid}",
                            email=f"{uid}@psn.local",
                            password_hash="x",
                            role="student",
                        )
                    )
            await db.commit()

    async def _cleanup(self, user_id: str, event_ids=()):
        """删除该用户相关的所有画像/事实数据，保证测试可重复运行。"""
        from app.data.database import get_db_session
        from app.data.models import (
            LearningRecord,
            UserProfile,
            UserKnowledgeState,
            Memory,
            MemoryTag,
            EventIdempotency,
            ChatSession,
        )
        from sqlalchemy import delete, select

        async with get_db_session() as db:
            # EventIdempotency 全局唯一，删除以 user_id 为前缀的（测试统一用 {user_id}: 前缀）
            for eid in event_ids:
                await db.execute(
                    delete(EventIdempotency).where(
                        EventIdempotency.event_id == eid
                    )
                )
            await db.execute(
                delete(EventIdempotency).where(
                    EventIdempotency.event_id.like(f"{user_id}:%")
                )
            )
            await db.execute(
                delete(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id)
            )
            await db.execute(
                delete(UserProfile).where(UserProfile.user_id == user_id)
            )
            await db.execute(
                delete(LearningRecord).where(LearningRecord.user_id == user_id)
            )
            mem_ids = (
                await db.execute(
                    select(Memory.id).where(Memory.user_id == user_id)
                )
            ).scalars().all()
            if mem_ids:
                await db.execute(
                    delete(MemoryTag).where(MemoryTag.memory_id.in_(mem_ids))
                )
            await db.execute(
                delete(Memory).where(Memory.user_id == user_id)
            )
            await db.execute(
                delete(ChatSession).where(ChatSession.user_id == user_id)
            )
            await db.commit()

    async def _seed_attempt_evidence(self, user_id, question_id, session_id, row_id, attempt_id, correct):
        """按 T01 口径落一条 PracticeAttempt，使 LearningRecord 事件可被引用为答题证据。"""
        from app.data.database import get_db_session
        from app.data.models import (
            Course, KnowledgeGraphVersion, Question,
            PracticeAttempt, PracticeSession, PracticeSessionQuestion,
        )
        from sqlalchemy import delete, select

        async with get_db_session() as db:
            await db.execute(delete(PracticeAttempt).where(PracticeAttempt.id == attempt_id))
            await db.execute(delete(PracticeSession).where(PracticeSession.id == session_id))
            if (await db.execute(select(Course).where(Course.id == "psn-course"))).scalar_one_or_none() is None:
                db.add(Course(id="psn-course", code="psn-calculus", name="高等数学", subject="math"))
                await db.flush()
            if (await db.execute(select(KnowledgeGraphVersion).where(KnowledgeGraphVersion.id == "psn-version"))).scalar_one_or_none() is None:
                db.add(KnowledgeGraphVersion(id="psn-version", course_id="psn-course", version="1", name="V1"))
                await db.flush()
            if (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none() is None:
                db.add(Question(
                    id=question_id, content="求解 x", question_type="numeric_fill",
                    answer="x=1", answer_spec={"kind": "numeric_fill"}, category="高数",
                    course_id="psn-course", version_id="psn-version",
                ))
                await db.flush()
            if (await db.execute(select(PracticeSession).where(PracticeSession.id == session_id))).scalar_one_or_none() is None:
                db.add(PracticeSession(
                    id=session_id, user_id=user_id, mode="practice", status="completed",
                    course_id="psn-course", version_id="psn-version", config_snapshot={},
                    random_seed=1, idempotency_key=f"{session_id}-key",
                ))
                await db.flush()
                db.add(PracticeSessionQuestion(
                    id=row_id, session_id=session_id, question_id=question_id,
                    position=1, snapshot={},
                ))
                await db.flush()
            db.add(PracticeAttempt(
                id=attempt_id, user_id=user_id, session_id=session_id,
                session_question_id=row_id, question_id=question_id,
                user_answer="x=1" if correct else "x=2", correct=correct,
                grading_snapshot={"correct_answer": "x=1" if correct else "x=2"},
                idempotency_key=f"{attempt_id}-key",
            ))
            await db.commit()

    async def _enqueue(self, facade, user_id, event, event_id=None):
        """阻止 worker 懒启动，确定性入队。"""
        with patch.object(
            facade, "_ensure_batch_worker_started", return_value=None
        ):
            return await facade.record_event(
                user_id, dict(event), event_id=event_id
            )

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

class TestProfileSnapshotBasics(ProfileTestBase):
    """get / refresh / invalidate 三个核心接口。"""

    @pytest.mark.asyncio
    async def test_get_profile_snapshot_rebuilds_from_facts(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade

        user_id = "psn_basic_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        facade = MemoryPersistenceFacade()
        snapshot = await facade.get_profile_snapshot(user_id)

        assert snapshot.user_id == user_id
        assert isinstance(snapshot.to_dict(), dict)
        assert snapshot.total_questions == 0  # 空用户默认

    @pytest.mark.asyncio
    async def test_refresh_persists_snapshot(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.profile_application import ProfileSnapshotRepository
        from app.data.database import get_db_session
        from app.data.models import UserProfile
        from sqlalchemy import select

        user_id = "psn_refresh_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        facade = MemoryPersistenceFacade()
        snapshot = await facade.refresh_profile_snapshot(user_id)

        # user_profiles 表应已持久化
        async with get_db_session() as db:
            row = (
                await db.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.version == snapshot.version

    @pytest.mark.asyncio
    async def test_invalidate_expires_cache_and_persisted_snapshot(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager

        user_id = "psn_invalidate_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        facade = MemoryPersistenceFacade()
        await facade.refresh_profile_snapshot(user_id)
        cache = get_cache_manager()
        key = facade._profile_snapshot_cache_key(user_id)
        assert key in cache.l1_cache

        await facade.invalidate_profile_snapshot(user_id)
        assert key not in cache.l1_cache
        from app.services.profile_application import ProfileSnapshotRepository
        repo = ProfileSnapshotRepository(facade._session_factory)
        assert await repo.get(user_id) is None
        # invalidate 不抛异常（Redis down 也可忽略）
        await facade.invalidate_profile_snapshot(user_id)

    @pytest.mark.asyncio
    async def test_get_uses_cache_after_refresh(self):
        """refresh 后缓存命中，get 不应再次重建。"""
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager

        user_id = "psn_cachehit_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        facade = MemoryPersistenceFacade()
        await facade.refresh_profile_snapshot(user_id)

        cache = get_cache_manager()
        cache.l1_cache.clear()

        with patch.object(
            facade, "_build_profile_snapshot", new=AsyncMock()
        ) as mock_build:
            # 缓存已填充，直接命中，不应重建
            await facade.get_profile_snapshot(user_id)
            assert not mock_build.called


class TestSnapshotIdempotency(ProfileTestBase):
    """同一事实数据连续 refresh 两次 → 业务画像完全一致。"""

    @pytest.mark.asyncio
    async def test_refresh_twice_identical_business_fields(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade

        user_id = "psn_idem_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        # 写入固定事实数据
        facade = MemoryPersistenceFacade()
        base = {
            "event_type": "answer_correct",
            "question_content": "求极限 lim(x->0) sinx/x",
            "category": "极限",
            "is_correct": True,
            "difficulty": 3,
            "time_spent": 60,
        }
        for i in range(4):
            await self._enqueue(
                facade, user_id, base, event_id=f"{user_id}:evt-c{i}"
            )
        batch = _drain_queue(facade)
        await facade._flush_batch(batch)
        await facade.trigger_skill_recalculation(user_id)

        s1 = await facade.refresh_profile_snapshot(user_id)
        s2 = await facade.refresh_profile_snapshot(user_id)

        d1, d2 = s1.to_dict(), s2.to_dict()
        # generated_at 为重建时间戳（预期变化），其余业务字段必须一致
        d1.pop("generated_at", None)
        d2.pop("generated_at", None)
        assert d1 == d2
        assert s1.total_questions == s2.total_questions
        assert s1.correct_rate == s2.correct_rate
        assert s1.skills == s2.skills


class TestProfileRebuild(ProfileTestBase):
    """删除 user_profiles + 清缓存 → 重新 get 业务画像一致。"""

    @pytest.mark.asyncio
    async def test_profile_rebuild_after_delete(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.profile_application import ProfileSnapshotRepository
        from app.services.cache import get_cache_manager

        user_id = "psn_rebuild_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        # 1. 写入事实
        facade = MemoryPersistenceFacade()
        base = {
            "event_type": "answer_correct",
            "question_content": "求导数 dy/dx",
            "category": "导数",
            "is_correct": True,
            "difficulty": 3,
        }
        for i in range(3):
            await self._enqueue(
                facade, user_id, base, event_id=f"{user_id}:rebuild-e{i}"
            )
        await facade._flush_batch(_drain_queue(facade))
        await facade.trigger_skill_recalculation(user_id)

        # 2. 生成画像
        original = await facade.refresh_profile_snapshot(user_id)

        # 3. 删除 user_profiles 快照
        repo = ProfileSnapshotRepository(facade._session_factory)
        assert await repo.delete(user_id) is True

        # 4. 清缓存
        await facade.invalidate_profile_snapshot(user_id)

        # 5. 重新 get → 从事实层重建
        rebuilt = await facade.get_profile_snapshot(user_id)

        od = original.to_dict()
        rd = rebuilt.to_dict()
        od.pop("generated_at", None)
        rd.pop("generated_at", None)
        assert od == rd
        assert rebuilt.total_questions == original.total_questions


class TestRedisDown(ProfileTestBase):
    """Redis 不可用时：Snapshot / Agent / Recommendation 均正常，不 500。"""

    @pytest.mark.asyncio
    async def test_redis_down_snapshot_still_works(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager

        user_id = "psn_redisdown_user"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        # 模拟 Redis down：redis=None + L1 清空
        cache = get_cache_manager()
        cache.redis = None
        cache.l1_cache.clear()

        facade = MemoryPersistenceFacade()
        snapshot = await facade.get_profile_snapshot(user_id)
        assert snapshot.user_id == user_id
        assert snapshot.total_questions == 0  # 从 DB/事实层正常获得，未抛异常

    @pytest.mark.asyncio
    async def test_redis_down_agent_profile_format_works(self):
        """Agent 画像格式化在 Redis down 时可正常工作。"""
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager
        from agent_core.agent import MathAgent

        user_id = "psn_redisdown_agent"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        cache = get_cache_manager()
        cache.redis = None
        cache.l1_cache.clear()

        facade = MemoryPersistenceFacade()
        snapshot = await facade.get_profile_snapshot(user_id)

        # Agent 的 _format_skill_profile_for_llm 必须接受 ProfileSnapshot
        text = MathAgent._format_skill_profile_for_llm(snapshot)
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_redis_down_recommendation_profile_works(self):
        """Recommendation 读取画像在 Redis down 时正常（含降级默认值）。"""
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager
        from app.services.rag_recommender import RAGRecommender

        user_id = "psn_redisdown_rag"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        cache = get_cache_manager()
        cache.redis = None
        cache.l1_cache.clear()

        facade = MemoryPersistenceFacade()
        await facade.refresh_profile_snapshot(user_id)

        recommender = RAGRecommender()
        profile = await recommender._get_user_profile(user_id)
        # 正常返回 dict（含降级默认值），不抛异常
        assert "correct_rate" in profile
        assert "total_questions" in profile


class TestUserIsolation(ProfileTestBase):
    """user_A / user_B：DB / cache / snapshot / skill / event 全部隔离。"""

    @pytest.mark.asyncio
    async def test_snapshot_and_fact_isolation(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.cache import get_cache_manager

        user_a, user_b = "psn_user_a", "psn_user_b"
        await self._ensure_users([user_a, user_b])
        await self._cleanup(user_a)
        await self._cleanup(user_b)

        facade = MemoryPersistenceFacade()
        base_a = {
            # T01 证据口径：只有 practice_answer + 独立作答 + 可溯源 attempt 才计入正确率；
            # 旧的 answer_correct（聊天侧事件）已被刻意排除在掌握度证据之外。
            "event_type": "practice_answer",
            "question_id": "PSN-Q1",
            "question_content": "A 的题目",
            "category": "极限",
            "is_correct": True,
            "difficulty": 3,
            "user_answer": "x=1",
            "metadata_": {"session_id": "psn-sess-a", "attempt_id": "psn-att-a1"},
        }
        base_b = {
            "event_type": "practice_answer",
            "question_id": "PSN-Q2",
            "question_content": "B 的题目",
            "category": "导数",
            "is_correct": False,
            "difficulty": 4,
            "user_answer": "x=2",
            "metadata_": {"session_id": "psn-sess-b", "attempt_id": "psn-att-b1"},
        }
        await self._seed_attempt_evidence(
            "psn_user_a", "PSN-Q1", "psn-sess-a", 1, "psn-att-a1", True)
        await self._seed_attempt_evidence(
            "psn_user_b", "PSN-Q2", "psn-sess-b", 2, "psn-att-b1", False)
        import copy
        event_a1 = copy.deepcopy(base_a)
        event_a2 = copy.deepcopy(base_a)
        event_a2["metadata_"] = dict(base_a["metadata_"], attempt_id="psn-att-a2")
        await self._enqueue(facade, user_a, event_a1, event_id=f"{user_a}:e1")
        await self._enqueue(facade, user_a, event_a2, event_id=f"{user_a}:e2")
        await self._enqueue(facade, user_b, base_b, event_id=f"{user_b}:e1")
        await facade._flush_batch(_drain_queue(facade))
        await facade.trigger_skill_recalculation(user_a)
        await facade.trigger_skill_recalculation(user_b)

        sa = await facade.refresh_profile_snapshot(user_a)
        sb = await facade.refresh_profile_snapshot(user_b)

        # 事实隔离
        assert await self._count_records(user_a) == 2
        assert await self._count_records(user_b) == 1

        # 快照业务隔离
        assert sa.total_questions == 2
        assert sb.total_questions == 1
        assert sa.correct_rate == 1.0
        assert sb.correct_rate == 0.0

        # 缓存 key 隔离
        cache = get_cache_manager()
        key_a = facade._profile_snapshot_cache_key(user_a)
        key_b = facade._profile_snapshot_cache_key(user_b)
        assert key_a != key_b
        a_cached = await cache.get(key_a)
        b_cached = await cache.get(key_b)
        assert a_cached is not None
        assert b_cached is not None
        assert a_cached["user_id"] == user_a
        assert b_cached["user_id"] == user_b
        # A 的缓存不会命中 B：清空 L1 后重新 get，必须返回 A 自己的画像（user_profiles 回源）
        cache.l1_cache.clear()
        refreshed_a = await facade.get_profile_snapshot(user_a)
        assert refreshed_a.user_id == user_a
        assert refreshed_a.total_questions == 2  # A 的数据，而非 B

    @pytest.mark.asyncio
    async def test_skill_isolation(self):
        from app.services.skill_aggregator import SkillAggregator
        from app.data.database import get_db_session
        from app.data.models import UserKnowledgeState
        # T01 后读取路径按 calculation_version 判定新旧；缺当前版本的 state 会被
        # 视为过期投影并从作答记录重算（本测试无作答 → 状态为空）。
        from app.services.learning_projection import policy_version

        user_a, user_b = "psn_skill_a", "psn_skill_b"
        await self._ensure_users([user_a, user_b])
        await self._cleanup(user_a)
        await self._cleanup(user_b)

        async with get_db_session() as db:
            db.add_all([
                UserKnowledgeState(user_id=user_a, knowledge_point_code="limit", attempts_count=2, correct_count=1, mastery=0.45, confidence=0.3, calculation_version=policy_version()),
                UserKnowledgeState(user_id=user_b, knowledge_point_code="derivative", attempts_count=2, correct_count=1, mastery=0.5, confidence=0.3, calculation_version=policy_version()),
            ])
            await db.commit()

        agg = SkillAggregator()
        skills_a = await agg.get_all_skills(user_a)
        skills_b = await agg.get_all_skills(user_b)
        assert {item["skill_code"] for item in skills_a} == {"limit"}
        assert {item["skill_code"] for item in skills_b} == {"derivative"}


class TestSkillAggregatorIdempotency(ProfileTestBase):
    """Compatibility command and canonical reads remain deterministic."""

    @pytest.mark.asyncio
    async def test_recalculate_twice_identical_and_no_duplicates(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        from app.services.skill_aggregator import SkillAggregator

        user_id = "psn_skill_idem"
        await self._ensure_users([user_id])
        await self._cleanup(user_id)

        facade = MemoryPersistenceFacade()
        base = {
            "event_type": "answer_correct",
            "question_content": "求极限",
            "category": "极限",
            "is_correct": True,
            "difficulty": 3,
        }
        for i in range(5):
            await self._enqueue(
                facade, user_id, base, event_id=f"{user_id}:si-e{i}"
            )
        await facade._flush_batch(_drain_queue(facade))

        agg = SkillAggregator()
        n1 = await agg.recalculate_skills(user_id)
        skills1 = await agg.get_all_skills(user_id)

        n2 = await agg.recalculate_skills(user_id)
        skills2 = await agg.get_all_skills(user_id)

        assert n1 == n2
        assert skills1 == skills2  # 同一批事实结果完全一致
        # (user_id, skill_code) 唯一
        codes = [s["skill_code"] for s in skills1]
        assert len(codes) == len(set(codes))


class TestEventIdempotency(ProfileTestBase):
    """相同 event_id 重复投递 → 事实记录只增加 1 次。"""

    @pytest.mark.asyncio
    async def test_same_event_id_inserts_once(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade

        user_id = "psn_event_idem"
        event_id = f"{user_id}:evt-dup"
        await self._ensure_users([user_id])
        await self._cleanup(user_id, [event_id])

        facade = MemoryPersistenceFacade()
        event = {
            "event_type": "answer_correct",
            "question_content": "求极限 lim(x->0) sinx/x",
            "category": "极限",
            "is_correct": True,
            "difficulty": 3,
        }
        for _ in range(3):
            await self._enqueue(facade, user_id, event, event_id=event_id)

        batch = _drain_queue(facade)
        assert len(batch) == 3
        await facade._flush_batch(batch)

        assert await self._count_records(user_id) == 1

        # EventIdempotency 已记录
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
        from agent_core.memory_persistence import MemoryPersistenceFacade

        user_id = "psn_event_distinct"
        await self._ensure_users([user_id])
        await self._cleanup(user_id, [f"{user_id}:e1", f"{user_id}:e2"])

        facade = MemoryPersistenceFacade()
        event = {
            "event_type": "answer_correct",
            "question_content": "求导数",
            "category": "导数",
            "is_correct": True,
        }
        await self._enqueue(facade, user_id, event, event_id=f"{user_id}:e1")
        await self._enqueue(facade, user_id, event, event_id=f"{user_id}:e2")
        await facade._flush_batch(_drain_queue(facade))

        assert await self._count_records(user_id) == 2


# ── PostgreSQL 兼容性静态断言 ──

BANNED_SQL_PATTERNS = [
    "ON DUPLICATE KEY UPDATE",
    "GROUP_CONCAT",
    "JSON_SET",
    "JSON_EXTRACT",
]

_DIALECT_AUDIT_FILES = [
    "app/services/profile_service.py",
    "app/services/skill_aggregator.py",
    "app/services/error_book_sync.py",
    "app/services/memory_store.py",
    "app/services/profile_analyzer.py",
    "app/services/profile_application.py",
    "agent_core/memory_persistence.py",
    "app/api/profile_api.py",
]


def _find_banned_sql_in_file(path: Path):
    """用 AST 提取非 docstring 字符串字面量，检查是否含方言 SQL 关键字。"""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    docstrings.add(val)

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node in docstrings:
                continue
            upper = node.value.upper()
            for kw in BANNED_SQL_PATTERNS:
                if kw in upper:
                    found.append((kw, node.lineno))
    return found


class TestPostgresqlCompatibility:
    """正式代码路径中不得再出现 MySQL/SQLite 专用 SQL。"""

    @pytest.mark.parametrize(
        "rel_path", _DIALECT_AUDIT_FILES
    )
    def test_no_mysql_sqlite_specific_sql(self, rel_path):
        root = Path(__file__).resolve().parents[1]
        target = root / rel_path
        assert target.exists(), f"审计文件不存在: {rel_path}"

        found = _find_banned_sql_in_file(target)
        assert not found, (
            f"{rel_path} 中存在 MySQL/SQLite 专用 SQL: {found} "
            f"（正式 PostgreSQL 语义下不可用）"
        )

    def test_no_banned_sql_anywhere_in_audit_files(self):
        """聚合断言：所有审计文件均无方言 SQL（报告用）。"""
        root = Path(__file__).resolve().parents[1]
        violations = {}
        for rel in _DIALECT_AUDIT_FILES:
            target = root / rel
            if not target.exists():
                violations[rel] = "文件不存在"
                continue
            found = _find_banned_sql_in_file(target)
            if found:
                violations[rel] = found
        assert not violations, f"方言 SQL 残留: {violations}"
