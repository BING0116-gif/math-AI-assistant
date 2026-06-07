"""
LLM 服务模块 — 统一管理大语言模型调用。

当前阶段：通义千问 DashScope API（兼容 OpenAI SDK）
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
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
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
    - analyze_question_difficulty(): AI难度分析
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
        if "localhost" in self.api_base or "127.0.0.1" in self.api_base:
            self.provider = LLMProvider.LOCAL

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
    ) -> LLMResponse:
        start = time.time()

        if use_cache:
            cache_key = self._make_cache_key(prompt, system_prompt, model or self.model)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        messages = self._build_messages(prompt, system_prompt)

        try:
            response = await self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
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

            if use_cache:
                self._add_to_cache(cache_key, result)

            return result
        except Exception as e:
            logger.error(f"LLM生成失败: {e}", exc_info=True)
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        messages = self._build_messages(prompt, system_prompt)
        try:
            stream = await self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
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

    async def analyze_question_difficulty(
        self, question_content: str, category: str
    ) -> Dict[str, Any]:
        system_prompt = (
            "你是一位数学教育专家。请分析以下数学题目的难度等级。\n"
            "请严格按照 JSON 格式返回：\n"
            '{"estimated_difficulty": 数字1-5, "reason": "理由", '
            '"knowledge_points": ["知识点1", "知识点2"]}\n'
            "难度定义：1=入门 2=基础 3=标准 4=进阶 5=挑战"
        )
        prompt = f"题目分类: {category}\n\n题目内容:\n{question_content}"
        response = await self.generate(prompt=prompt, system_prompt=system_prompt, temperature=0.1)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(content)
        except (json.JSONDecodeError, IndexError):
            return {"estimated_difficulty": 3, "reason": "AI分析失败", "knowledge_points": [category]}

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