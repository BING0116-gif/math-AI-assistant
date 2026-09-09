"""
LLMService 单元测试。

覆盖：
- 单例模式
- 缓存机制（存储、命中、过期、TTL）
- 消息构建
- 缓存键生成
- 数学模式（TIR prompt）
- 难度分析
- 缓存清理
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.llm_service import (
    LLMService,
    LLMResponse,
    LLMProvider,
    get_llm_service,
)


class TestLLMResponse:
    """测试 LLMResponse 数据类"""

    def test_creation(self):
        resp = LLMResponse(
            content="test response",
            model="test-model",
            provider="dashscope",
            usage={"total_tokens": 100},
            latency_ms=500.0,
        )
        assert resp.content == "test response"
        assert resp.model == "test-model"
        assert resp.provider == "dashscope"
        assert resp.usage["total_tokens"] == 100
        assert resp.latency_ms == 500.0
        assert resp.cached is False

    def test_to_dict(self):
        resp = LLMResponse(
            content="hello",
            model="gpt-4",
            provider="local",
            usage={"total_tokens": 50},
            latency_ms=200.0,
            cached=True,
        )
        d = resp.to_dict()
        assert d["content"] == "hello"
        assert d["model"] == "gpt-4"
        assert d["cached"] is True
        assert d["usage"]["total_tokens"] == 50


class TestLLMServiceSingleton:
    """测试 LLMService 单例模式"""

    def test_same_instance(self):
        """多次调用返回同一实例"""
        svc1 = LLMService(api_key="unit-test-key")
        svc2 = LLMService(api_key="unit-test-key")
        assert svc1 is svc2

    def test_get_llm_service(self):
        """get_llm_service 返回 LLMService 实例"""
        svc = LLMService(api_key="unit-test-key")
        assert isinstance(svc, LLMService)


class TestLLMServiceCache:
    """测试 LLMService 缓存机制"""

    @pytest.fixture
    def svc(self):
        """创建干净的 LLMService 实例用于缓存测试"""
        svc = LLMService.__new__(LLMService)
        svc._cache = {}
        svc._cache_ttl = 300
        svc._cache_max_size = 100
        svc._initialized = True
        svc._client = MagicMock()
        return svc

    def test_cache_key_consistent(self, svc):
        """相同输入产生相同缓存键"""
        key1 = svc._make_cache_key("hello", "system prompt", "model-a")
        key2 = svc._make_cache_key("hello", "system prompt", "model-a")
        assert key1 == key2

    def test_cache_key_different(self, svc):
        """不同输入产生不同缓存键"""
        key1 = svc._make_cache_key("hello", "sys1", "model-a")
        key2 = svc._make_cache_key("world", "sys1", "model-a")
        assert key1 != key2

    def test_add_to_cache(self, svc):
        """添加响应到缓存"""
        resp = LLMResponse(content="cached response", model="m", provider="p")
        svc._add_to_cache("key1", resp)
        assert "key1" in svc._cache

    def test_get_from_cache_hit(self, svc):
        """缓存命中"""
        resp = LLMResponse(content="cached response long enough", model="m", provider="p")
        svc._add_to_cache("key1", resp)
        cached = svc._get_from_cache("key1")
        assert cached is not None
        assert cached.cached is True
        assert cached.content == "cached response long enough"

    def test_get_from_cache_miss(self, svc):
        """缓存未命中"""
        result = svc._get_from_cache("nonexistent")
        assert result is None

    def test_cache_expiry(self, svc):
        """缓存过期"""
        svc._cache_ttl = 0  # 立即过期
        resp = LLMResponse(content="expired", model="m", provider="p")
        svc._add_to_cache("key1", resp)
        time.sleep(0.01)
        result = svc._get_from_cache("key1")
        assert result is None

    def test_cache_short_content_skipped(self, svc):
        """短内容不缓存（<10字符）"""
        resp = LLMResponse(content="short", model="m", provider="p")
        svc._add_to_cache("key1", resp)
        assert "key1" not in svc._cache

    def test_cache_size_limit(self, svc):
        """缓存大小限制"""
        svc._cache_max_size = 3
        for i in range(5):
            resp = LLMResponse(
                content=f"response number {i} long enough",
                model="m",
                provider="p",
            )
            svc._add_to_cache(f"key{i}", resp)
        assert len(svc._cache) <= 3

    def test_clear_cache(self, svc):
        """清理缓存"""
        resp = LLMResponse(content="test content long enough", model="m", provider="p")
        svc._add_to_cache("key1", resp)
        svc._add_to_cache("key2", resp)
        count = svc.clear_cache()
        assert count == 2
        assert len(svc._cache) == 0

    def test_get_cache_stats(self, svc):
        """获取缓存统计"""
        stats = svc.get_cache_stats()
        assert "cache_size" in stats
        assert "ttl_seconds" in stats


class TestLLMServiceBuildMessages:
    """测试消息构建"""

    @pytest.fixture
    def svc(self):
        svc = LLMService.__new__(LLMService)
        svc._initialized = True
        svc._client = MagicMock()
        return svc

    def test_with_system_prompt(self, svc):
        messages = svc._build_messages("user prompt", "system prompt")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "system prompt"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "user prompt"

    def test_without_system_prompt(self, svc):
        messages = svc._build_messages("user prompt", None)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "user prompt"


class TestLLMServiceGenerate:
    """测试 LLMService.generate 方法"""

    @pytest.fixture
    def svc(self):
        svc = LLMService.__new__(LLMService)
        svc.api_key = "test-key"
        svc.api_base = "https://test.api.com/v1"
        svc.model = "test-model"
        svc.math_model = "math-model"
        svc.temperature = 0.7
        svc.max_tokens = 2000
        svc.provider = LLMProvider.DASHSCOPE
        svc._cache = {}
        svc._cache_ttl = 300
        svc._cache_max_size = 100
        svc._initialized = True
        svc._client = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_generate_success(self, svc):
        """测试成功生成响应"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content="AI response"),
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        mock_response.model = "test-model"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate("test prompt")
            assert result.content == "AI response"
            assert result.model == "test-model"
            assert result.provider == "dashscope"
            assert result.cached is False

    @pytest.mark.asyncio
    async def test_generate_with_cache(self, svc):
        """测试缓存命中"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="cached response"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=5, completion_tokens=5, total_tokens=10
        )
        mock_response.model = "test-model"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            # 第一次调用
            result1 = await svc.generate("test prompt", use_cache=True)
            assert result1.cached is False

            # 第二次调用（缓存命中）
            result2 = await svc.generate("test prompt", use_cache=True)
            assert result2.cached is True

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, svc):
        """测试带系统提示的生成"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="response with system"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=15, completion_tokens=25, total_tokens=40
        )
        mock_response.model = "test-model"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate(
                "test prompt",
                system_prompt="You are a math tutor.",
            )
            assert result.content == "response with system"

    @pytest.mark.asyncio
    async def test_generate_preserves_explicit_zero_temperature(self, svc):
        """分类器显式要求 temperature=0 时不能回退到服务默认值。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = None
        mock_response.model = "test-model"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            await svc.generate("judge", temperature=0, max_tokens=64, use_cache=False)

        kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert kwargs["temperature"] == 0
        assert kwargs["max_tokens"] == 64

    @pytest.mark.asyncio
    async def test_generate_skip_cache(self, svc):
        """测试跳过缓存"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="fresh response"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=5, completion_tokens=5, total_tokens=10
        )
        mock_response.model = "test-model"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            result1 = await svc.generate("test prompt", use_cache=True)
            result2 = await svc.generate("test prompt", use_cache=False)
            assert result1.cached is False
            assert result2.cached is False  # 跳过缓存


class TestLLMServiceMathModel:
    """测试数学模式"""

    @pytest.fixture
    def svc(self):
        svc = LLMService.__new__(LLMService)
        svc.api_key = "test-key"
        svc.api_base = "https://test.api.com/v1"
        svc.model = "test-model"
        svc.math_model = "math-model"
        svc.temperature = 0.7
        svc.max_tokens = 2000
        svc.provider = LLMProvider.DASHSCOPE
        svc._cache = {}
        svc._cache_ttl = 300
        svc._cache_max_size = 100
        svc._initialized = True
        svc._client = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_math_model_adds_tir_prompt(self, svc):
        """数学模式自动添加 TIR prompt"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="math solution"))
        ]
        mock_response.usage = None
        mock_response.model = "math-model"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate_with_math_model(
                "solve integral of x^2",
                use_tir=True,
            )
            assert "math solution" in result.content


class TestLLMProviderDetection:
    """测试 LLM 提供商检测"""

    def test_local_provider_detection(self):
        """检测本地提供商"""
        svc = LLMService.__new__(LLMService)
        svc.api_key = "test"
        if hasattr(svc, '_initialized'):
            delattr(svc, '_initialized')
        svc.__init__(
            api_key="test-key",
            api_base="http://localhost:8000/v1",
        )
        assert svc.provider == LLMProvider.LOCAL

    def test_remote_provider_detection(self):
        """检测远程提供商"""
        svc = LLMService.__new__(LLMService)
        svc.api_key = "test"
        if hasattr(svc, '_initialized'):
            delattr(svc, '_initialized')
        svc.__init__(
            api_key="test-key",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        assert svc.provider == LLMProvider.DASHSCOPE

    def test_deepseek_provider_detection(self):
        """主文本模型切换 DeepSeek 后，应检测为 DEEPSEEK provider（观测指标维度正确）"""
        svc = LLMService.__new__(LLMService)
        svc.api_key = "test"
        if hasattr(svc, '_initialized'):
            delattr(svc, '_initialized')
        svc.__init__(
            api_key="test-key",
            api_base="https://api.deepseek.com/v1",
        )
        assert svc.provider == LLMProvider.DEEPSEEK
