"""Track A 9.4 缓存分层单元测试：开关语义、命中/未命中指标、故障降级。"""

import os
import sys

import pytest

os.environ.setdefault("APP_ENV", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.observability import CACHE_HITS, CACHE_MISSES
from app.services.cache_layers import (
    embedding_cache_key,
    vector_search_cache_key,
    cached_lookup,
)


def _counter_value(counter, layer: str) -> float:
    return counter.labels(layer)._value.get()


class _Delta:
    """记录某层 hit/miss 计数器在测试块前后的增量。"""

    def __init__(self, layer: str):
        self.layer = layer
        self.hit0 = _counter_value(CACHE_HITS, layer)
        self.miss0 = _counter_value(CACHE_MISSES, layer)

    def hits(self) -> float:
        return _counter_value(CACHE_HITS, self.layer) - self.hit0

    def misses(self) -> float:
        return _counter_value(CACHE_MISSES, self.layer) - self.miss0


@pytest.fixture()
def fresh_cache(monkeypatch):
    """每个用例使用全新 L1 缓存，避免键互相污染。"""
    from app.services import cache as cache_module

    manager = cache_module.CacheManager("redis://localhost:6379/0")
    monkeypatch.setattr(cache_module, "_cache_manager", manager)
    return manager


@pytest.mark.asyncio
async def test_disabled_layer_runs_factory_without_metrics(fresh_cache):
    calls = []

    async def factory():
        calls.append(1)
        return "result"

    delta = _Delta("embedding")
    result = await cached_lookup(
        "embedding", False, "cache:emb:m:k", 60, factory
    )

    assert result == "result"
    assert len(calls) == 1
    assert delta.hits() == 0 and delta.misses() == 0


@pytest.mark.asyncio
async def test_enabled_layer_caches_and_counts(fresh_cache):
    calls = []

    async def factory():
        calls.append(1)
        return {"v": [0.1, 0.2]}

    key = embedding_cache_key("hello", "test-model")
    delta = _Delta("embedding")

    first = await cached_lookup("embedding", True, key, 60, factory)
    second = await cached_lookup("embedding", True, key, 60, factory)

    assert first == second == {"v": [0.1, 0.2]}
    assert len(calls) == 1  # 第二次命中缓存
    assert delta.misses() == 1 and delta.hits() == 1


@pytest.mark.asyncio
async def test_cache_read_failure_falls_back_to_factory(monkeypatch):
    from app.services import cache as cache_module

    class _BrokenManager:
        async def get(self, key):
            raise RuntimeError("redis down")

        async def set(self, key, value, ttl=3600, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr(
        cache_module, "_cache_manager", _BrokenManager()
    )

    async def factory():
        return "direct"

    result = await cached_lookup("vector_search", True, "k", 60, factory)
    assert result == "direct"


@pytest.mark.asyncio
async def test_factory_exception_propagates_and_not_cached(fresh_cache):
    calls = []

    async def factory():
        calls.append(1)
        raise ValueError("boom")

    key = embedding_cache_key("x", "m")
    with pytest.raises(ValueError):
        await cached_lookup("embedding", True, key, 60, factory)

    assert len(calls) == 1
    assert await fresh_cache.get(key) is None


def test_embedding_cache_key_distinguishes_text_and_model():
    assert embedding_cache_key("a", "m1") != embedding_cache_key("b", "m1")
    assert embedding_cache_key("a", "m1") != embedding_cache_key("a", "m2")
    assert embedding_cache_key("a", "m1") == embedding_cache_key("a", "m1")


def test_vector_search_cache_key_distinguishes_all_params():
    base = vector_search_cache_key("q", None, None, 10, 0.7)
    assert base != vector_search_cache_key("q2", None, None, 10, 0.7)
    assert base != vector_search_cache_key("q", "calculus", None, 10, 0.7)
    assert base != vector_search_cache_key("q", None, (2, 4), 10, 0.7)
    assert base != vector_search_cache_key("q", None, None, 5, 0.7)
    assert base != vector_search_cache_key("q", None, None, 10, 0.8)
    # 相同参数稳定同键
    assert base == vector_search_cache_key("q", None, None, 10, 0.7)
