"""
LLM 服务模块 — 统一管理大语言模型调用。

当前技术栈：
  - 主文本模型：DeepSeek（OpenAI 兼容 API，settings.LLM_API_BASE / LLM_MODEL）
  - 快速模型（分类/难度/AI 分析）：settings.LLM_MATH_MODEL（默认 qwen-turbo）
  - 识图链路：千问 VL（vision_tool / qwen-vl-*），独立于本模块
后续阶段：切换至本地部署模型（接口不变，只改配置）

设计要点：
- 单例模式，全局复用
- 内存缓存（5分钟TTL，LRU淘汰，最多100条）
- 流式响应支持（AsyncGenerator）
- TIR 数学推理模式
- 降级处理（JSON解析失败返回默认值）
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple

from openai import AsyncOpenAI

from app.config.settings import MODEL_CAPABILITIES, settings

logger = logging.getLogger(__name__)

MODEL_CAPABILITY_NAMES = frozenset({"tool_call", "json_output", "vision"})


class ModelCapabilityError(RuntimeError):
    """模型无法满足调用方强制要求的高级能力。"""

    def __init__(self, model: str, capability: str, *, unknown_model: bool = False):
        self.model = model
        self.capability = capability
        self.code = (
            "MODEL_CAPABILITY_UNKNOWN"
            if unknown_model
            else "MODEL_CAPABILITY_UNSUPPORTED"
        )
        if unknown_model:
            message = (
                f"模型 {model!r} 未在 MODEL_CAPABILITIES 中登记，"
                f"无法确认其 {capability!r} 能力"
            )
        else:
            message = f"模型 {model!r} 不支持要求的 {capability!r} 能力"
        super().__init__(message)


def require_model_capabilities(model: str, capabilities: Iterable[str]) -> None:
    """校验强制能力；未知模型、未知能力和明确不支持均 fail-closed。"""
    normalized_model = (model or "").strip()
    configured = MODEL_CAPABILITIES.get(normalized_model)
    requested = tuple(dict.fromkeys(capabilities))
    if not requested:
        return
    if configured is None:
        raise ModelCapabilityError(
            normalized_model or "<empty>", requested[0], unknown_model=True
        )
    for capability in requested:
        if capability not in MODEL_CAPABILITY_NAMES:
            raise ValueError(f"未知模型能力: {capability!r}")
        if configured.get(capability) is not True:
            raise ModelCapabilityError(normalized_model, capability)


def require_model_capability(model: str, capability: str) -> None:
    """单项能力校验的便捷入口。"""
    require_model_capabilities(model, (capability,))


def model_capability_status(model: str, capabilities: Iterable[str]) -> dict[str, Any]:
    """返回无副作用的能力诊断，供 provider-status/readiness 复用。"""
    required = tuple(dict.fromkeys(capabilities))
    try:
        require_model_capabilities(model, required)
    except (ModelCapabilityError, ValueError) as exc:
        return {
            "ok": False,
            "model": model,
            "required": list(required),
            "reason": str(exc),
            "error_code": getattr(exc, "code", "MODEL_CAPABILITY_INVALID"),
        }
    return {
        "ok": True,
        "model": model,
        "required": list(required),
        "reason": "supported",
    }


class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    DASHSCOPE = "dashscope"
    LOCAL = "local"


class LLMResponse:
    def __init__(
        self,
        content: str,
        model: str,
        provider: str,
        usage: Optional[Dict[str, int]] = None,
        latency_ms: float = 0.0,
        cached: bool = False,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.cached = cached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }


class LLMService:
    """
    LLM 服务管理器（单例模式）

    设计要点：
    - 全项目共享一个 LLMService 实例（单例模式）
    - 通用对话和数学推理共用同一个模型
    - 数学推理使用 generate_with_math_model() 方法（自动添加 TIR prompt）
    - 后续切换本地模型只需修改 .env 中的 LLM_API_BASE 和 LLM_MODEL

    核心方法：
    - generate(): 非流式生成
    - generate_stream(): 流式生成
    - generate_with_math_model(): 数学专用（自动添加 TIR prompt）
    """

    _instance: Optional[LLMService] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        math_model: Optional[str] = None,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.api_key = api_key or settings.LLM_API_KEY or settings.DASHSCOPE_API_KEY
        self.api_base = api_base or settings.LLM_API_BASE
        self.model = model or settings.LLM_MODEL
        self.math_model = math_model or settings.LLM_MATH_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS

        self.provider = LLMProvider.DASHSCOPE
        api_base_l = (self.api_base or "").lower()
        if "localhost" in api_base_l or "127.0.0.1" in api_base_l:
            self.provider = LLMProvider.LOCAL
        elif "deepseek" in api_base_l:
            self.provider = LLMProvider.DEEPSEEK
            # 端点是 DeepSeek 时，千问模型名必然 404（与 application.py 主模型对齐逻辑一致），
            # 数学/快速模型同步对齐，避免 qwen-* 遗留配置打向 DeepSeek。
            if self.math_model.startswith("qwen"):
                self.math_model = "deepseek-chat"

        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base)
        self._cache: Dict[str, Tuple[LLMResponse, float]] = {}
        self._cache_ttl: int = 300
        self._cache_max_size: int = 100
        self._initialized = True

        logger.info(
            f"LLMService 初始化: provider={self.provider.value}, "
            f"model={self.model}, math_model={self.math_model}"
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
        required_capabilities: Iterable[str] = (),
    ) -> LLMResponse:
        start = time.time()
        request_model = model or self.model
        require_model_capabilities(request_model, required_capabilities)

        if use_cache:
            cache_key = self._make_cache_key(prompt, system_prompt, request_model)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        messages = self._build_messages(prompt, system_prompt)

        try:
            response = await self._client.chat.completions.create(
                model=request_model,
                messages=messages,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=self.max_tokens if max_tokens is None else max_tokens,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else {}

            result = LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider.value,
                usage=usage,
                latency_ms=(time.time() - start) * 1000,
            )
            from app.observability import AI_CALLS, AI_LATENCY, AI_TOKENS
            metric_model = (response.model or model or self.model or "unknown")[:80]
            metric_provider = self.provider.value
            AI_CALLS.labels(metric_provider, metric_model, "success").inc()
            AI_LATENCY.labels(metric_provider, metric_model).observe(result.latency_ms / 1000)
            AI_TOKENS.labels(metric_provider, metric_model, "input").inc(usage.get("prompt_tokens", 0))
            AI_TOKENS.labels(metric_provider, metric_model, "output").inc(usage.get("completion_tokens", 0))

            if use_cache:
                self._add_to_cache(cache_key, result)

            return result
        except Exception as e:
            from app.observability import AI_CALLS
            AI_CALLS.labels(self.provider.value, (model or self.model or "unknown")[:80], "error").inc()
            logger.error(f"LLM生成失败: {e}", exc_info=True)
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        required_capabilities: Iterable[str] = (),
    ) -> AsyncGenerator[str, None]:
        request_model = model or self.model
        require_model_capabilities(request_model, required_capabilities)
        messages = self._build_messages(prompt, system_prompt)
        try:
            stream = await self._client.chat.completions.create(
                model=request_model,
                messages=messages,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=self.max_tokens if max_tokens is None else max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM流式生成失败: {e}", exc_info=True)
            yield f"\n\n[生成错误: {str(e)}]"

    async def generate_with_math_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        use_tir: bool = True,
    ) -> LLMResponse:
        if use_tir:
            prompt = prompt + (
                "\n\n【TIR模式要求】"
                "\n1. 先用自然语言分析问题思路"
                "\n2. 编写 Python 代码进行计算或验证（用 ```python 包裹）"
                "\n3. 根据代码执行结果给出最终答案"
                "\n4. 格式：最后用 **最终答案：** 标记结果"
            )
        return await self.generate(
            prompt=prompt, system_prompt=system_prompt, model=self.math_model,
        )

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _make_cache_key(self, prompt: str, system_prompt: Optional[str], model: str) -> str:
        import hashlib
        return hashlib.md5(f"{model}:{system_prompt or ''}:{prompt}".encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[LLMResponse]:
        if key not in self._cache:
            return None
        entry, timestamp = self._cache[key]
        if time.time() - timestamp > self._cache_ttl:
            del self._cache[key]
            return None
        entry.cached = True
        return entry

    def _add_to_cache(self, key: str, response: LLMResponse) -> None:
        if not response.content or len(response.content) < 10:
            return
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (response, time.time())

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        return {"cache_size": len(self._cache), "ttl_seconds": self._cache_ttl}


def get_llm_service() -> LLMService:
    """获取 LLM 服务单例。数学推理使用 generate_with_math_model() 方法。"""
    return LLMService()
