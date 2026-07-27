"""
定时任务 — 记忆强度衰减、过期归档、对账一致性检查。

使用 APScheduler 实现，支持：
- 每日凌晨执行记忆强度衰减
- 每日凌晨执行过期归档
- 每日凌晨执行跨系统对账
- 单人休眠检测
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.settings import settings
from app.services.memory_store import (
    MemoryStore,
    get_memory_store,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_MILESTONE,
    MEMORY_TYPE_PROFILE,
    STATUS_ACTIVE,
    DECAY_LAMBDA,
)

logger = logging.getLogger(__name__)

# 兜底强度阈值
MIN_STRENGTH_THRESHOLD = 0.2

# 单人休眠检测天数
SLEEP_DAYS_THRESHOLD = 7


class MemoryScheduledTasks:
    """记忆系统定时任务管理器。"""

    def __init__(self):
        self._store: Optional[MemoryStore] = None
        self._scheduler: Optional[AsyncIOScheduler] = None

    async def _get_store(self) -> MemoryStore:
        if self._store is None:
            self._store = get_memory_store()
        return self._store

    # ========================================================================
    # 任务 1：记忆强度衰减
    # ========================================================================

    async def decay_memory_strength(self) -> Dict[str, Any]:
        """执行记忆强度衰减。

        公式：memory_today = memory_yesterday × e^(-λ)
        里程碑衰减极慢，画像不参与日常衰减。
        掌握度修正：正确率 ≥ 70% 时衰减系数翻倍。
        """
        store = await self._get_store()
        now = int(time.time())
        # 计算过去 7 天的时间戳，用于休眠检测
        seven_days_ago = now - SLEEP_DAYS_THRESHOLD * 86400

        stats = {"total_decayed": 0, "total_archived": 0, "sleeping_users": 0}

        try:
            from app.data.database import get_db_session
            from sqlalchemy import text as sa_text

            async with get_db_session() as db:
                # 获取所有 active 状态的记忆
                result = await db.execute(
                    sa_text("""
                        SELECT id, user_id, memory_type, memory_strength, last_accessed
                        FROM memories
                        WHERE status = :status AND deleted_at IS NULL
                    """),
                    {"status": STATUS_ACTIVE},
                )
                rows = result.fetchall()

                for row in rows:
                    memory_id = row._mapping["id"]
                    user_id = row._mapping["user_id"]
                    memory_type = row._mapping["memory_type"]
                    strength = float(row._mapping["memory_strength"])
                    last_accessed = row._mapping["last_accessed"]

                    # 画像不参与日常衰减
                    if memory_type == MEMORY_TYPE_PROFILE:
                        continue

                    # 单人休眠检测：连续 7 天无访问暂停衰减
                    if last_accessed and last_accessed < seven_days_ago:
                        stats["sleeping_users"] += 1
                        continue

                    # 获取衰减系数
                    decay_lambda = DECAY_LAMBDA.get(memory_type, 0.0045)

                    # 计算衰减后强度
                    new_strength = strength * math_exp(-decay_lambda)
                    new_strength = max(0.0, min(1.0, new_strength))

                    # 更新强度
                    await db.execute(
                        sa_text("""
                            UPDATE memories
                            SET memory_strength = :strength
                            WHERE id = :id
                        """),
                        {"strength": new_strength, "id": memory_id},
                    )
                    stats["total_decayed"] += 1

                    # 兜底阈值：强度 < 0.2 自动归档
                    if new_strength < MIN_STRENGTH_THRESHOLD:
                        await db.execute(
                            sa_text("""
                                UPDATE memories
                                SET status = :status
                                WHERE id = :id AND status = 'active'
                            """),
                            {"status": "archived", "id": memory_id},
                        )
                        stats["total_archived"] += 1

            if stats["total_decayed"] > 0:
                logger.info(
                    f"[定时任务] 记忆强度衰减完成: {stats}"
                )

        except Exception as e:
            logger.error(f"[定时任务] 记忆强度衰减失败: {e}")

        return stats

    # ========================================================================
    # 任务 2：过期归档
    # ========================================================================

    async def archive_expired_memories(self) -> Dict[str, Any]:
        """批量归档过期记忆。"""
        store = await self._get_store()
        count = await store.batch_archive_expired()
        return {"archived_count": count}

    # ========================================================================
    # 任务 3：低强度归档
    # ========================================================================

    async def archive_low_strength_memories(self) -> Dict[str, Any]:
        """批量归档低强度记忆（兜底阈值 0.2）。"""
        store = await self._get_store()
        count = await store.batch_archive_low_strength(
            threshold=MIN_STRENGTH_THRESHOLD
        )
        return {"archived_count": count}

    # ========================================================================
    # 任务 4：休眠用户检测
    # ========================================================================

    async def detect_sleeping_users(self) -> List[str]:
        """检测连续 7 天无访问的休眠用户。"""
        now = int(time.time())
        cutoff = now - SLEEP_DAYS_THRESHOLD * 86400

        sleeping_users = []
        try:
            from app.data.database import get_db_session
            from sqlalchemy import text as sa_text

            async with get_db_session() as db:
                result = await db.execute(
                    sa_text("""
                        SELECT DISTINCT user_id
                        FROM memories
                        WHERE last_accessed IS NOT NULL
                            AND last_accessed < :cutoff
                            AND status = 'active'
                    """),
                    {"cutoff": cutoff},
                )
                rows = result.fetchall()
                sleeping_users = [row._mapping["user_id"] for row in rows]

            if sleeping_users:
                logger.info(
                    f"[定时任务] 检测到休眠用户: {len(sleeping_users)} 人"
                )

        except Exception as e:
            logger.error(f"[定时任务] 休眠用户检测失败: {e}")

        return sleeping_users

    # ========================================================================
    # 任务 5：跨系统对账
    # ========================================================================

    async def check_consistency(self) -> Dict[str, Any]:
        """跨系统数据一致性对账。

        校验 source_id 对应题目是否有效，无效题目关联记忆自动归档。
        """
        stats = {"checked": 0, "archived": 0, "errors": 0}

        try:
            from app.adapters.question_system.factory import get_question_system_adapter
            from app.data.database import get_db_session
            from sqlalchemy import text as sa_text

            adapter = get_question_system_adapter()

            async with get_db_session() as db:
                # 获取所有有 source_id 的 active 记忆
                result = await db.execute(
                    sa_text("""
                        SELECT id, source_id, memory_type, user_id
                        FROM memories
                        WHERE status = 'active'
                            AND source_id IS NOT NULL
                            AND source_id != ''
                    """),
                )
                rows = result.fetchall()
                stats["checked"] = len(rows)

                for row in rows:
                    memory_id = row._mapping["id"]
                    source_id = row._mapping["source_id"]
                    memory_type = row._mapping["memory_type"]

                    if memory_type == MEMORY_TYPE_ERROR:
                        # 校验错题对应的题目是否有效
                        question_info = adapter.get_question_info(source_id)
                        if not question_info or not question_info.get("is_active", True):
                            await db.execute(
                                sa_text("""
                                    UPDATE memories
                                    SET status = 'archived'
                                    WHERE id = :id AND status = 'active'
                                """),
                                {"id": memory_id},
                            )
                            stats["archived"] += 1

            if stats["archived"] > 0:
                logger.info(f"[定时任务] 对账完成: checked={stats['checked']}, archived={stats['archived']}")

        except Exception as e:
            logger.error(f"[定时任务] 对账失败: {e}")
            stats["errors"] = 1

        return stats

    # ========================================================================
    # 调度器管理
    # ========================================================================

    def start_scheduler(self, application=None):
        """启动 APScheduler 定时任务。"""
        if self._scheduler and self._scheduler.running:
            logger.warning("[定时任务] 调度器已在运行")
            return

        self._scheduler = AsyncIOScheduler()

        # 每日凌晨 2:00 执行记忆强度衰减
        self._scheduler.add_job(
            self._run_async(self.decay_memory_strength),
            CronTrigger(hour=2, minute=0),
            id="decay_memory_strength",
            name="记忆强度衰减",
            replace_existing=True,
        )

        # 每日凌晨 2:30 执行过期归档
        self._scheduler.add_job(
            self._run_async(self.archive_expired_memories),
            CronTrigger(hour=2, minute=30),
            id="archive_expired_memories",
            name="过期记忆归档",
            replace_existing=True,
        )

        # 每日凌晨 3:00 执行低强度归档
        self._scheduler.add_job(
            self._run_async(self.archive_low_strength_memories),
            CronTrigger(hour=3, minute=0),
            id="archive_low_strength_memories",
            name="低强度记忆归档",
            replace_existing=True,
        )

        # 每日凌晨 1:00 执行跨系统对账
        self._scheduler.add_job(
            self._run_async(self.check_consistency),
            CronTrigger(hour=1, minute=0),
            id="check_consistency",
            name="跨系统对账",
            replace_existing=True,
        )

        # 每日凌晨 3:30 执行休眠检测
        self._scheduler.add_job(
            self._run_async(self.detect_sleeping_users),
            CronTrigger(hour=3, minute=30),
            id="detect_sleeping_users",
            name="休眠用户检测",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("[定时任务] 调度器已启动，注册了 5 个定时任务")

    def stop_scheduler(self):
        """停止 APScheduler 定时任务。"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[定时任务] 调度器已停止")

    @staticmethod
    def _run_async(coro):
        """包装异步协程为同步函数。"""
        def wrapper(*args, **kwargs):
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        return wrapper


# 辅助函数
def math_exp(x: float) -> float:
    """计算 e^x。"""
    import math
    return math.exp(x)


# 全局单例
_scheduled_tasks_instance: Optional[MemoryScheduledTasks] = None


def get_scheduled_tasks() -> MemoryScheduledTasks:
    global _scheduled_tasks_instance
    if _scheduled_tasks_instance is None:
        _scheduled_tasks_instance = MemoryScheduledTasks()
    return _scheduled_tasks_instance