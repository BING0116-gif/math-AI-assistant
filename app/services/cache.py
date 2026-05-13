import pickle
import logging
from typing import Optional, Any, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[Any] = None
        self.l1_cache: Dict[str, Any] = {}
        self.l1_max_size = 1000
        self.l1_hits = 0
        self.l2_hits = 0
        self.misses = 0

    async def initialize(self):
        try:
            import redis.asyncio as aioredis

            self.redis = aioredis.from_url(
                self.redis_url, decode_responses=False
            )
            await self.redis.ping()
            logger.info("Redis 连接成功")
        except ImportError:
            logger.warning("redis 库未安装，将仅使用 L1 缓存")
            self.redis = None
        except Exception as e:
            logger.warning(f"Redis 连接失败，将仅使用 L1 缓存: {e}")
            self.redis = None

    async def get(self, key: str) -> Optional[Any]:
        if key in self.l1_cache:
            self.l1_hits += 1
            return self.l1_cache[key]

        if self.redis:
            try:
                cached = await self.redis.get(f"cache:{key}")
                if cached:
                    self.l2_hits += 1
                    value = pickle.loads(cached)
                    self._set_l1(key, value)
                    return value
            except Exception as e:
                logger.debug(f"Redis 读取失败: {e}")

        self.misses += 1
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
        use_l1: bool = True,
        use_l2: bool = True,
    ):
        if use_l1:
            self._set_l1(key, value)

        if use_l2 and self.redis:
            try:
                serialized = pickle.dumps(value)
                await self.redis.setex(f"cache:{key}", ttl, serialized)
            except Exception as e:
                logger.debug(f"Redis 写入失败: {e}")

    async def delete(self, key: str):
        self.l1_cache.pop(key, None)
        if self.redis:
            try:
                await self.redis.delete(f"cache:{key}")
            except Exception:
                pass

    async def invalidate_pattern(self, pattern: str):
        keys_to_remove = [k for k in self.l1_cache if pattern in k]
        for k in keys_to_remove:
            del self.l1_cache[k]

        if self.redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(
                        cursor, match=f"cache:{pattern}", count=100
                    )
                    if keys:
                        await self.redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception:
                pass

    def _set_l1(self, key: str, value: Any):
        if len(self.l1_cache) >= self.l1_max_size:
            evict_key = next(iter(self.l1_cache))
            del self.l1_cache[evict_key]
        self.l1_cache[key] = value

    @property
    def stats(self) -> Dict[str, Any]:
        total = self.l1_hits + self.l2_hits + self.misses
        return {
            "l1_size": len(self.l1_cache),
            "l1_max_size": self.l1_max_size,
            "hits": {
                "l1": self.l1_hits,
                "l2": self.l2_hits,
                "total": self.l1_hits + self.l2_hits,
            },
            "misses": self.misses,
            "hit_rate": (self.l1_hits + self.l2_hits) / max(total, 1),
            "l1_hit_rate": self.l1_hits / max(total, 1),
        }

    async def close(self):
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass


_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def cache_result(ttl: int = 3600, prefix: str = ""):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            cache_key = f"{prefix}{func.__name__}:{str(args)}:{str(kwargs)}"

            cached = await cache_manager.get(cache_key)
            if cached is not None:
                return cached

            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator