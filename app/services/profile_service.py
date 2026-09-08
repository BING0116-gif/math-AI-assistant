"""
用户画像系统 — 兼容包装层（已降级）。

架构收敛后，MemoryPersistenceFacade 是唯一画像应用入口。
本模块不再承担画像生成 / 独立业务事实 / MySQL upsert 职责，
仅保留旧调用方（Admin Dashboard、出题系统事件、验证脚本）所需的
公共方法签名，统一转发到 MemoryPersistenceFacade 的统一快照实现。

历史职责（已移除）：
- ON DUPLICATE KEY UPDATE 的 MySQL 专用 SQL（PostgreSQL 不可用）
- 独立写入 user_profiles 作为业务真值
- 独立 Redis 缓存路径（统一收敛到 cache.py）
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProfileService:
    """用户画像服务（兼容包装）。

    所有公开方法均转发到 MemoryPersistenceFacade 的统一 ProfileSnapshot。
    user_profiles 仅是 materialized snapshot（可重建），不是事实来源。
    """

    async def _get_facade(self):
        from agent_core.memory_persistence import MemoryPersistenceFacade
        return MemoryPersistenceFacade()

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户画像（旧版 dict 结构，仅供旧调用方兼容）。"""
        facade = await self._get_facade()
        snapshot = await facade.get_profile_snapshot(user_id)
        return {
            "summary_text": snapshot.summary_text,
            "version": snapshot.version,
            "updated_at": 0,
            "full_profile": snapshot.to_dict(),
        }

    async def get_profile_summary(self, user_id: str) -> str:
        """获取画像摘要文本（用于注入 Prompt）。"""
        facade = await self._get_facade()
        snapshot = await facade.get_profile_snapshot(user_id)
        return snapshot.summary_text

    async def incremental_update(
        self,
        user_id: str,
        high_category: str = "",
        category: str = "",
        mastery_score: float = 0.0,
        correct_rate: float = 0.0,
    ) -> bool:
        """增量更新（兼容入口）。

        已停止作为业务事实更新机制：
        - 不再直接写 user_profiles（避免 MySQL 方言与真值污染）
        - 仅使画像快照缓存失效，下次读取由 Facade 从事实层重建
        """
        try:
            facade = await self._get_facade()
            await facade.invalidate_profile_snapshot(user_id)
            logger.debug(
                f"[画像服务] 增量更新(已降级为快照失效): user={user_id}, category={category}"
            )
            return True
        except Exception as e:
            logger.error(f"[画像服务] 增量更新失败: {e}")
            return False

    async def full_refresh(self, user_id: str) -> bool:
        """全量更新画像（从事实层完整重建快照）。"""
        try:
            facade = await self._get_facade()
            await facade.refresh_profile_snapshot(user_id)
            logger.info(f"[画像服务] 全量更新完成: user={user_id}")
            return True
        except Exception as e:
            logger.error(f"[画像服务] 全量更新失败: {e}")
            return False


# 全局单例
_profile_service_instance: Optional[ProfileService] = None


def get_profile_service() -> ProfileService:
    global _profile_service_instance
    if _profile_service_instance is None:
        _profile_service_instance = ProfileService()
    return _profile_service_instance
