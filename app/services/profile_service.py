"""
用户画像系统 — 画像生成、增量更新、Redis 缓存。

提供：
- 画像生成（事件触发/定时触发/冷启动）
- Redis 缓存机制
- 缓存失效降级查 MySQL
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ProfileService:
    """用户画像服务。"""

    def __init__(self):
        self._redis = None
        self._redis_available = False

    async def _get_redis(self):
        """延迟初始化 Redis 客户端。"""
        if self._redis is not None:
            return self._redis

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info("[画像服务] Redis 连接成功")
        except Exception as e:
            logger.warning(f"[画像服务] Redis 不可用，降级直查 MySQL: {e}")
            self._redis_available = False

        return self._redis

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户完整画像。

        优先从 Redis 缓存读取，缓存未命中则从 MySQL 加载。
        """
        # 尝试从缓存读取
        cached = await self._get_cached_profile(user_id)
        if cached:
            return cached

        # 缓存未命中，从 MySQL 加载
        profile = await self._load_from_mysql(user_id)

        # 写入缓存
        if profile:
            await self._set_cached_profile(user_id, profile)

        return profile or self._cold_start_profile(user_id)

    async def get_profile_summary(self, user_id: str) -> str:
        """获取画像摘要文本（用于注入 Prompt）。"""
        profile = await self.get_profile(user_id)
        return profile.get("summary_text", "")

    async def incremental_update(
        self,
        user_id: str,
        high_category: str = "",
        category: str = "",
        mastery_score: float = 0.0,
        correct_rate: float = 0.0,
    ) -> bool:
        """增量更新画像（事件触发）。"""
        try:
            profile = await self._load_from_mysql(user_id)
            if not profile:
                profile = self._cold_start_profile(user_id)

            # 更新知识点掌握度
            mastery = profile.get("full_profile", {}).get("knowledge_mastery", {})
            if category:
                mastery[category] = {
                    "mastery_score": mastery_score,
                    "correct_rate": correct_rate,
                    "updated_at": int(time.time()),
                }

            profile["full_profile"]["knowledge_mastery"] = mastery

            # 更新摘要
            profile["summary_text"] = self._generate_summary(profile["full_profile"])

            # 保存到 MySQL
            await self._save_to_mysql(user_id, profile)

            # 删除缓存
            await self._invalidate_cache(user_id)

            logger.info(f"[画像服务] 增量更新完成: user={user_id}, category={category}")
            return True

        except Exception as e:
            logger.error(f"[画像服务] 增量更新失败: {e}")
            return False

    async def full_refresh(self, user_id: str) -> bool:
        """全量更新画像（基于全部历史数据）。"""
        try:
            profile = await self._load_from_mysql(user_id)
            if not profile:
                profile = self._cold_start_profile(user_id)

            # 重新生成摘要
            profile["summary_text"] = self._generate_summary(profile["full_profile"])
            profile["version"] = profile.get("version", 0) + 1
            profile["updated_at"] = int(time.time())

            # 保存到 MySQL
            await self._save_to_mysql(user_id, profile)

            # 删除缓存
            await self._invalidate_cache(user_id)

            logger.info(f"[画像服务] 全量更新完成: user={user_id}")
            return True

        except Exception as e:
            logger.error(f"[画像服务] 全量更新失败: {e}")
            return False

    def _cold_start_profile(self, user_id: str) -> Dict[str, Any]:
        """冷启动：新用户通用基础画像模板。"""
        now = int(time.time())
        profile = {
            "summary_text": "该用户为新用户，暂无学习数据。建议从基础题目开始学习。",
            "version": 1,
            "updated_at": now,
            "full_profile": {
                "knowledge_mastery": {},
                "weak_points": [],
                "strong_points": [],
                "error_patterns": {
                    "common_errors": [],
                    "frequent_error_types": {},
                },
                "preferences": {
                    "difficulty_mode": "adaptive",
                    "preferred_categories": [],
                    "daily_goal_minutes": 30,
                },
                "learning_habits": {
                    "avg_time_per_question": 0,
                    "total_questions": 0,
                    "correct_rate": 0.0,
                },
            },
        }
        return profile

    def _generate_summary(self, full_profile: Dict[str, Any]) -> str:
        """从完整画像生成摘要文本。"""
        mastery = full_profile.get("knowledge_mastery", {})
        weak_points = full_profile.get("weak_points", [])
        error_patterns = full_profile.get("error_patterns", {})
        preferences = full_profile.get("preferences", {})

        parts = []

        # 薄弱知识点
        if weak_points:
            weak_str = "、".join(weak_points[:5])
            parts.append(f"薄弱知识点：{weak_str}")

        # 掌握度
        if mastery:
            low_mastery = [
                k for k, v in mastery.items()
                if isinstance(v, dict) and v.get("correct_rate", 1.0) < 0.6
            ]
            if low_mastery:
                parts.append(f"需加强：{'、'.join(low_mastery[:3])}")

        # 错误模式
        common_errors = error_patterns.get("common_errors", [])
        if common_errors:
            parts.append(f"易犯错误：{'、'.join(common_errors[:2])}")

        # 偏好
        diff_mode = preferences.get("difficulty_mode", "adaptive")
        if diff_mode == "fixed":
            parts.append("固定难度模式")

        return "；".join(parts) if parts else "该用户暂无详细画像数据。"

    # ========================================================================
    # Redis 缓存操作
    # ========================================================================

    async def _get_cached_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """从 Redis 获取缓存的画像。"""
        if not self._redis_available:
            return None

        try:
            redis = await self._get_redis()
            if redis is None:
                return None

            cache_key = f"math-agent:profile:{user_id}"
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                logger.debug(f"[画像服务] 缓存命中: user={user_id}")
                return data
        except Exception as e:
            logger.warning(f"[画像服务] 缓存读取失败: {e}")
            self._redis_available = False

        return None

    async def _set_cached_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """将画像写入 Redis 缓存。"""
        if not self._redis_available:
            return False

        try:
            redis = await self._get_redis()
            if redis is None:
                return False

            cache_key = f"math-agent:profile:{user_id}"
            ttl = settings.MEMORY_PROFILE_CACHE_TTL
            await redis.setex(cache_key, ttl, json.dumps(profile, ensure_ascii=False))
            logger.debug(f"[画像服务] 缓存写入: user={user_id}, TTL={ttl}s")
            return True
        except Exception as e:
            logger.warning(f"[画像服务] 缓存写入失败: {e}")
            return False

    async def _invalidate_cache(self, user_id: str) -> bool:
        """删除用户画像缓存。"""
        if not self._redis_available:
            return False

        try:
            redis = await self._get_redis()
            if redis is None:
                return False

            cache_key = f"math-agent:profile:{user_id}"
            await redis.delete(cache_key)
            logger.debug(f"[画像服务] 缓存已删除: user={user_id}")
            return True
        except Exception as e:
            logger.warning(f"[画像服务] 缓存删除失败: {e}")
            return False

    # ========================================================================
    # MySQL 操作
    # ========================================================================

    async def _load_from_mysql(self, user_id: str) -> Optional[Dict[str, Any]]:
        """从 MySQL 加载用户画像。"""
        try:
            from app.data.database import get_db_session
            from sqlalchemy import text as sa_text

            async with get_db_session() as db:
                result = await db.execute(
                    sa_text("""
                        SELECT summary_text, full_profile_json, version, updated_at
                        FROM user_profiles
                        WHERE user_id = :user_id
                    """),
                    {"user_id": user_id},
                )
                row = result.fetchone()
                if row is None:
                    return None

                return {
                    "summary_text": row._mapping["summary_text"],
                    "version": row._mapping["version"],
                    "updated_at": row._mapping["updated_at"],
                    "full_profile": json.loads(row._mapping["full_profile_json"]),
                }
        except Exception as e:
            logger.error(f"[画像服务] MySQL 加载失败: {e}")
            return None

    async def _save_to_mysql(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """保存画像到 MySQL。"""
        try:
            from app.data.database import get_db_session
            from sqlalchemy import text as sa_text

            async with get_db_session() as db:
                # UPSERT 操作
                await db.execute(
                    sa_text("""
                        INSERT INTO user_profiles
                        (user_id, summary_text, full_profile_json, version, updated_at)
                        VALUES
                        (:user_id, :summary_text, :full_profile_json, :version, :updated_at)
                        ON DUPLICATE KEY UPDATE
                            summary_text = VALUES(summary_text),
                            full_profile_json = VALUES(full_profile_json),
                            version = VALUES(version),
                            updated_at = VALUES(updated_at)
                    """),
                    {
                        "user_id": user_id,
                        "summary_text": profile.get("summary_text", ""),
                        "full_profile_json": json.dumps(
                            profile.get("full_profile", {}), ensure_ascii=False
                        ),
                        "version": profile.get("version", 1),
                        "updated_at": profile.get("updated_at", int(time.time())),
                    },
                )
                return True
        except Exception as e:
            logger.error(f"[画像服务] MySQL 保存失败: {e}")
            return False


# 全局单例
_profile_service_instance: Optional[ProfileService] = None


def get_profile_service() -> ProfileService:
    global _profile_service_instance
    if _profile_service_instance is None:
        _profile_service_instance = ProfileService()
    return _profile_service_instance