"""Track A 9.4 缓存分层：嵌入向量与向量检索结果的按层缓存。

所有层默认关闭，由 settings 按层显式开启（CACHE_EMBEDDINGS_ENABLED /
CACHE_VECTOR_SEARCH_ENABLED），开启与否不改变调用方语义。

键设计红线：
- 本模块提供的键只覆盖**全局内容**（公开题库的嵌入向量与向量检索结果），
  不含用户身份；用户作用域数据（工具结果、画像衍生结果等）必须先把
  user_id/作用域编入键并单列一层，禁止复用这里的无身份键。
- 缓存读写任何异常都只降级为直连执行，绝不阻断请求；工厂函数的异常
  原样上抛，失败结果不入缓存。

命中率统一打 mathai_cache_hit_total{layer} / mathai_cache_miss_total{layer}，
层关闭时不打点（避免 D4 命中率面板被禁用层的 0 值稀释）。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Awaitable, Callable, Optional, Tuple

from app.observability import CACHE_HITS, CACHE_MISSES

logger = logging.getLogger(__name__)

# §9.4：嵌入结果 24h（文本不变即有效）；向量检索 10min（题库发布/下架
# 的最大陈旧窗口，题库版本号尚未参与键前的兜底）。
EMBEDDING_TTL_SECONDS = 24 * 3600
VECTOR_SEARCH_TTL_SECONDS = 10 * 60


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_cache_key(text: str, model: str) -> str:
    return f"cache:emb:{model}:{_sha256(str(text))}"


def vector_search_cache_key(
    query: str,
    category_filter: Optional[str],
    difficulty_range: Optional[Tuple[int, int]],
    n_results: int,
    vector_weight: float,
) -> str:
    parts = [
        str(query or "").strip(),
        str(category_filter or ""),
        f"{difficulty_range[0]}-{difficulty_range[1]}" if difficulty_range else "",
        str(n_results),
        f"{vector_weight:.4f}",
    ]
    return "cache:vsearch:" + _sha256("\x1f".join(parts))


async def cached_lookup(
    layer: str,
    enabled: bool,
    key: str,
    ttl: int,
    factory: Callable[[], Awaitable[Any]],
) -> Any:
    """按层缓存地执行 factory()；层关闭或缓存异常时直连执行。"""
    if not enabled:
        return await factory()

    try:
        from app.services.cache import get_cache_manager

        cached = await get_cache_manager().get(key)
    except Exception as exc:
        logger.debug("缓存层 %s 读取失败，直连执行: %s", layer, exc)
        cached = None

    if cached is not None:
        CACHE_HITS.labels(layer).inc()
        return cached

    CACHE_MISSES.labels(layer).inc()
    result = await factory()
    try:
        from app.services.cache import get_cache_manager

        await get_cache_manager().set(key, result, ttl=ttl)
    except Exception as exc:
        logger.debug("缓存层 %s 写入失败（忽略）: %s", layer, exc)
    return result
