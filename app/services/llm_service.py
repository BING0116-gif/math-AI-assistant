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
- 跨厂商响应校验（空工具调用、截断、JSON 失败降级）
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
TRUNCATION_NOTICE = "\n\n[回答被截断，请重试或缩小问题范围。]"
JSON_PARTIAL_NOTICE = "\n\n[模型返回的 JSON 不完整，结果仅供诊断，请重试。]"


class LLMResponseValidationError(ValueError):
    """厂商响应不满足可安全消费的最小契约。异常文本可直接展示给用户。"""


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
        finish_reason: Optional[str] = None,
        partial: bool = False,
        parse_error: Optional[str] = None,
        parsed_json: Any = None,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.cached = cached
        self.finish_reason = finish_reason
        self.partial = partial
        self.parse_error = parse_error
        self.parsed_json = parsed_json

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
            "finish_reason": self.finish_reason,
            "partial": self.partial,
            "parse_error": self.parse_error,
            "parsed_json": self.parsed_json,
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
            if not response.choices:
                raise LLMResponseValidationError("模型未返回任何候选回答，请重试。")

            choice = response.choices[0]
            message = choice.message
            finish_reason_value = getattr(choice, "finish_reason", None)
            finish_reason = finish_reason_value if isinstance(finish_reason_value, str) else None
            self._validate_tool_calls(message, finish_reason)

            content = message.content or ""
            partial = finish_reason == "length"
            if partial:
                logger.warning(
                    "LLM 回答被截断: provider=%s model=%s finish_reason=length",
                    self.provider.value,
                    response.model or request_model,
                )
                content += TRUNCATION_NOTICE
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
                finish_reason=finish_reason,
                partial=partial,
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
        except LLMResponseValidationError as e:
            from app.observability import AI_CALLS
            AI_CALLS.labels(self.provider.value, request_model[:80], "error").inc()
            logger.error("LLM 响应校验失败: %s", e)
            raise
        except Exception as e:
            from app.observability import AI_CALLS
            AI_CALLS.labels(self.provider.value, request_model[:80], "error").inc()
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
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    yield choice.delta.content
                if getattr(choice, "finish_reason", None) == "length":
                    logger.warning(
                        "LLM 流式回答被截断: provider=%s model=%s finish_reason=length",
                        self.provider.value,
                        request_model,
                    )
                    yield TRUNCATION_NOTICE
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

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """生成 JSON；解析失败只重试一次，之后以 partial 结果安全降级。

        补括号恢复只用于提供诊断字段。调用方必须检查 ``partial``，不得把
        ``parsed_json`` 中的恢复值当作完整成功结果。
        """
        retry_prompt = prompt
        first_parse_error: Optional[str] = None

        for attempt in range(2):
            result = await self.generate(
                prompt=retry_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=False,
                required_capabilities=("json_output",),
            )
            raw_content = self._raw_content(result.content)
            try:
                if result.finish_reason == "length":
                    raise json.JSONDecodeError(
                        "response truncated with finish_reason=length",
                        raw_content,
                        len(raw_content),
                    )
                result.parsed_json = self._parse_json(raw_content)
                return result
            except (json.JSONDecodeError, ValueError) as exc:
                if first_parse_error is None:
                    first_parse_error = str(exc)
                logger.warning(
                    "LLM JSON 解析失败: provider=%s model=%s attempt=%s/2 error=%s",
                    self.provider.value,
                    model or self.model,
                    attempt + 1,
                    exc,
                )
                if attempt == 0:
                    retry_prompt = (
                        f"{prompt}\n\n上一次响应不是完整合法的 JSON。"
                        "请重新生成一次，只输出完整合法 JSON，不要使用 Markdown 代码围栏。"
                    )
                    continue

                result.partial = True
                result.parse_error = first_parse_error
                result.parsed_json = self._diagnose_truncated_json(raw_content)
                if JSON_PARTIAL_NOTICE not in result.content:
                    result.content += JSON_PARTIAL_NOTICE
                logger.error(
                    "LLM JSON 重试后仍解析失败，已标记 partial: provider=%s model=%s "
                    "original_error=%s final_error=%s",
                    self.provider.value,
                    model or self.model,
                    first_parse_error,
                    exc,
                )
                return result

        raise AssertionError("unreachable")

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _validate_tool_calls(message: Any, finish_reason: Optional[str]) -> None:
        """拒绝空工具调用；这是响应校验，不触发任何自动重试。

        当前直连 DeepSeek，不改写 tool-call id；接入代理网关时需回看 id 穿透。
        """
        tool_calls = getattr(message, "tool_calls", None)
        concrete_calls = tool_calls if isinstance(tool_calls, (list, tuple)) else None
        if finish_reason == "tool_calls" and not concrete_calls:
            logger.warning("拒绝空工具调用: finish_reason=tool_calls 但 tool_calls 为空")
            raise LLMResponseValidationError("模型返回了空工具调用，已拒绝处理，请重试。")
        if concrete_calls is None:
            return

        for index, call in enumerate(concrete_calls):
            function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
            name = function.get("name") if isinstance(function, dict) else getattr(function, "name", None)
            arguments = (
                function.get("arguments")
                if isinstance(function, dict)
                else getattr(function, "arguments", None)
            )
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(arguments, str)
                or not arguments.strip()
            ):
                logger.warning(
                    "拒绝空工具调用: index=%s name=%r arguments=%r",
                    index,
                    name,
                    arguments,
                )
                raise LLMResponseValidationError("模型返回了空工具调用，已拒绝处理，请重试。")

    @staticmethod
    def _raw_content(content: str) -> str:
        return content.removesuffix(TRUNCATION_NOTICE).strip()

    @staticmethod
    def _parse_json(content: str) -> Any:
        text = content.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)

    @staticmethod
    def _diagnose_truncated_json(content: str) -> Any:
        """尽力补齐闭合括号，仅返回诊断数据，绝不改变 partial 状态。"""
        text = content.strip()
        if not text or text[0] not in "[{":
            return None
        closing = {"{": "}", "[": "]"}
        stack: List[str] = []
        in_string = False
        escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in closing:
                stack.append(closing[char])
            elif char in "}]":
                if not stack or stack.pop() != char:
                    return None
        if in_string:
            return None
        try:
            return json.loads(text + "".join(reversed(stack)))
        except json.JSONDecodeError:
            return None

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
        if response.partial or not response.content or len(response.content) < 10:
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
