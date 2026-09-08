"""
VisionTool — 通义千问 VL（视觉-语言）多模态识别工具。

技术栈定位：识图链路固定使用千问 VL（qwen-vl-plus / qwen-vl-max），
不随主文本模型（DeepSeek）切换；API Key 复用 DASHSCOPE_API_KEY。
截图直接发给 Qwen-VL，由模型端到端理解图片内容（文字+公式+图形），
返回结构化的「题目描述 + LaTeX 公式 + 空间关系」。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger(__name__)

# API 配置（与现有 DashScope key 复用）
_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# VL 模型名称（按能力从高到低，可按需替换）
_VL_MODELS = [
    "qwen-vl-plus",           # 优先：数学理解强，支持流式
    "qwen-vl-max",            # 备选：更大规模
]


def _load_api_key(file_path: str = ".env") -> Optional[str]:
    """从项目配置（pydantic-settings）或环境变量加载 API Key。"""
    try:
        from app.config.settings import settings
        if settings.DASHSCOPE_API_KEY:
            return settings.DASHSCOPE_API_KEY
    except Exception:
        pass

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if api_key:
        return api_key

    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "DASHSCOPE_API_KEY":
                return v.strip()
    return None


def _img_to_base64(image_path: str) -> str:
    """将图片文件转换为 base64 字符串。"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _guess_mime(path: str) -> str:
    """根据文件扩展名猜测 MIME 类型。"""
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


def _build_llm_input(vl_output: str) -> str:
    """
    把 VL 的原始输出整理为发给解题 Agent 的用户输入。
    保留 LaTeX 原文，去掉多余解释。
    """
    lines = vl_output.strip().splitlines()
    cleaned = []
    skip_marker = False
    for line in lines:
        if line.strip().startswith("【题目】"):
            skip_marker = True
        if skip_marker:
            cleaned.append(line)
    result = "\n".join(cleaned) if cleaned else vl_output.strip()
    return (
        "请解答以下高等数学题目（图片识别结果）：\n\n"
        + result
    )


class VisionTool:
    """
    通义千问 VL（视觉-语言）多模态识别工具。

    将截图直接发给 Qwen-VL，返回题目结构化描述。

    Attributes:
        name: 工具名称
        description: 工具描述
    """

    # 默认系统提示词
    DEFAULT_SYSTEM_PROMPT = (
        "你是一个高数题目图像理解专家。用户会发来一张截图，"
        "请完成以下两步：\n\n"
        "【步骤 1：结构化提取】\n"
        "仔细阅读截图，提取题目中的所有信息，包括：\n"
        "- 题干文字（中文叙述）\n"
        "- 数学公式（用 LaTeX 表示，例如 $x^2+1$）\n"
        "- 几何图形描述（如坐标系、曲线、点、线段）\n"
        "- 选项内容（如 A/B/C/D）\n\n"
        "【步骤 2：输出格式】\n"
        "将提取结果按以下格式返回（不要加任何额外说明）：\n\n"
        "【题目】\n<题干文字>\n\n"
        "【公式】\n<LaTeX 公式，重要公式用独立段落 $$...$$>\n\n"
        "【图形描述】（如有）\n<坐标系、关键点位置等>\n\n"
        "【选项】（如有）\n<选项内容>\n\n"
        "【其他说明】（如有）\n<图注、补充条件等>\n"
    )

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        初始化 VisionTool。

        Args:
            model: VL 模型名称（默认使用 qwen-vl-plus）
            api_key: DashScope API Key（默认从环境变量或 .env 加载）
            timeout: 请求超时时间（秒）
        """
        self.name = "vision_tool"
        self.description = (
            "多模态图片理解：截图直接发给 Qwen-VL，"
            "输出题目文字、LaTeX 公式、图形空间关系的结构化描述。"
        )
        self._api_key = api_key or _load_api_key(".env")
        self._model = model or _VL_MODELS[0]
        self._base_url = _DASHSCOPE_BASE
        self._timeout = timeout

        if not self._api_key:
            logger.warning("DASHSCOPE_API_KEY not found in environment or .env file")

    @property
    def api_key_configured(self) -> bool:
        """检查 API Key 是否已配置。"""
        return bool(self._api_key)

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头。"""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_image_url(self, image_source: Union[str, Tuple[str, str]]) -> str:
        """
        构建图片 URL（支持本地文件或 data URL）。

        Args:
            image_source: 图片路径或 (mime_type, base64_data) 元组

        Returns:
            data URL 格式的图片地址
        """
        if isinstance(image_source, tuple):
            mime, b64 = image_source
            return f"data:{mime};base64,{b64}"

        # 本地文件
        path = image_source
        if not os.path.exists(path):
            raise FileNotFoundError(f"图片文件不存在: {path}")

        mime = _guess_mime(path)
        b64 = _img_to_base64(path)
        return f"data:{mime};base64,{b64}"

    def _build_messages(
        self,
        image_url: str,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建发送给 VL 模型的 messages。

        Args:
            image_url: 图片 data URL
            system_prompt: 系统提示词（可选）
            user_prompt: 用户提示词（可选）

        Returns:
            消息列表
        """
        system = system_prompt or self.DEFAULT_SYSTEM_PROMPT

        user_content: List[Dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        if user_prompt:
            user_content.insert(0, {"type": "text", "text": user_prompt})

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _get_models_to_try(self, model: Optional[str]) -> List[str]:
        """获取需要尝试的模型列表（按优先级排序）。"""
        preferred = model or self._model
        return [preferred] + [m for m in _VL_MODELS if m != preferred]

    # ── 同步 API 调用 ──────────────────────────────────────────────────────

    def _call_api_sync(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        **params,
    ) -> httpx.Response:
        """
        同步调用 API（stream=False）。

        Args:
            messages: 消息列表
            model: 模型名称
            **params: 额外参数

        Returns:
            httpx.Response 对象
        """
        headers = self._build_headers()
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **params,
        }

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response

    async def _call_api_async(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        stream: bool = False,
        **params,
    ) -> Union[httpx.Response, AsyncGenerator[bytes, None]]:
        """
        异步调用 API（修复版：正确管理HTTP客户端生命周期）。

        Args:
            messages: 消息列表
            model: 模型名称
            stream: 是否启用流式
            **params: 额外参数

        Returns:
            stream=False: httpx.Response 对象
            stream=True: 异步生成器（客户端在生成器内部创建和管理）
        """
        headers = self._build_headers()
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **params,
        }

        if stream:
            # 修复：将客户端创建移到生成器内部，避免过早关闭
            async def stream_generator():
                # 在生成器内部创建客户端，确保生命周期正确
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            yield chunk

            return stream_generator()
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response

    # ── 主识别方法 ─────────────────────────────────────────────────────────

    def recognize(
        self,
        image_source: Union[str, Tuple[str, str]],
        user_prompt: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将图片发给 VL 模型，获取题目结构化描述（同步版本）。

        Args:
            image_source: 图片文件路径或 (mime_type, base64_data) 元组
            user_prompt: 可选的自定义 prompt
            model: 可选，指定 VL 模型名称
            system_prompt: 可选，覆盖默认系统提示词

        Returns:
            {
                "success": bool,
                "llm_description": str,   # 发给解题 agent 的完整描述
                "raw_response": str,      # 模型原始输出（方便调试）
                "error": Optional[str],
                "model_used": str,        # 实际使用的模型名
            }
        """
        # 检查 API Key
        if not self._api_key:
            return self._error_result("DASHSCOPE_API_KEY 未配置，请在 .env 或环境变量中配置。")

        # 构造图片 URL
        try:
            image_url = self._build_image_url(image_source)
        except FileNotFoundError as e:
            return self._error_result(f"图片文件不存在: {e}")
        except Exception as e:
            return self._error_result(f"图片读取失败: {e}")

        # 构建消息
        messages = self._build_messages(image_url, system_prompt, user_prompt)

        # 尝试调用模型
        models_to_try = self._get_models_to_try(model)
        last_error = ""

        for try_model in models_to_try:
            try:
                response = self._call_api_sync(
                    messages,
                    model=try_model,
                    temperature=0.3,
                    max_tokens=2048,
                )
                data = response.json()
                return self._parse_response(data, try_model)

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.warning(f"VL 模型调用失败 ({try_model}): {last_error}")
                continue

            except httpx.RequestError as e:
                last_error = f"请求错误: {e}"
                logger.warning(f"VL 模型请求错误 ({try_model}): {last_error}")
                continue

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.error(f"VL 模型调用异常 ({try_model}): {last_error}")
                continue

        return self._error_result(f"所有 VL 模型调用均失败: {last_error}")

    def recognize_from_base64(
        self,
        mime: str,
        b64_data: str,
        user_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从 base64 数据直接调用（Streamlit 粘贴图片走此路径）。

        Args:
            mime: MIME 类型（如 "image/png"）
            b64_data: base64 编码的图片数据（不含前缀）
            user_prompt: 可选的自定义 prompt
            model: 可选，指定 VL 模型名称

        Returns:
            同 recognize() 方法
        """
        return self.recognize(
            image_source=(mime, b64_data),
            user_prompt=user_prompt,
            model=model,
        )

    # ── 异步流式识别 ────────────────────────────────────────────────────────

    async def recognize_stream(
        self,
        image_source: Union[str, Tuple[str, str]],
        user_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        异步流式识别（逐 token 返回）。

        Args:
            image_source: 图片文件路径或 (mime_type, base64_data) 元组
            user_prompt: 可选的自定义 prompt
            model: 可选，指定 VL 模型名称

        Yields:
            {
                "type": "token" | "complete" | "error",
                "content": str,           # type=token 时为 token 内容
                "success": bool,           # type=complete 时
                "llm_description": str,   # type=complete 时
                "raw_response": str,        # type=complete 时
                "model_used": str,          # type=complete 时
            }
        """
        if not self._api_key:
            yield {"type": "error", "content": "DASHSCOPE_API_KEY 未配置"}
            return

        try:
            image_url = self._build_image_url(image_source)
        except Exception as e:
            yield {"type": "error", "content": f"图片读取失败: {e}"}
            return

        messages = self._build_messages(image_url, user_prompt=user_prompt)
        models_to_try = self._get_models_to_try(model)
        last_error = ""

        for try_model in models_to_try:
            try:
                logger.info(f"VisionTool: 开始调用VL模型 [{try_model}] (流式模式)")
                stream_gen = await self._call_api_async(
                    messages,
                    model=try_model,
                    stream=True,
                    temperature=0.3,
                    max_tokens=2048,
                )

                buffer = b""
                full_response = ""
                chunk_count = 0
                token_usage: Dict[str, int] = {}

                async for chunk in stream_gen:
                    if chunk:
                        buffer += chunk
                        lines = buffer.split(b"\n\n")
                        for line in lines[:-1]:
                            line_str = line.decode("utf-8")
                            if line_str.startswith("data: "):
                                data_str = line_str[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    usage = data.get("usage") or {}
                                    if usage:
                                        token_usage = {
                                            "prompt_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                                            "completion_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
                                            "total_tokens": int(usage.get("total_tokens", 0) or 0),
                                        }
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full_response += content
                                        chunk_count += 1
                                        yield {"type": "token", "content": content}
                                except json.JSONDecodeError:
                                    continue
                        buffer = lines[-1]

                logger.info(
                    f"VisionTool: VL模型 [{try_model}] 调用成功, "
                    f"收到 {chunk_count} 个chunks, 总长度 {len(full_response)} 字符"
                )
                yield {
                    "type": "complete",
                    "success": True,
                    "llm_description": _build_llm_input(full_response),
                    "raw_response": full_response,
                    "model_used": try_model,
                    "token_usage": token_usage or None,
                }
                return

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"VisionTool: VL模型 [{try_model}] 流式调用失败: {last_error}\n"
                    f"错误类型: {type(e).__name__}"
                )
                continue

        yield {"type": "error", "content": f"所有 VL 模型调用均失败: {last_error}"}

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _parse_response(self, data: Dict[str, Any], model: str) -> Dict[str, Any]:
        """解析 API 响应。"""
        choices = data.get("choices", [])
        if not choices:
            return self._error_result(f"API 返回无 choices: {data}")

        msg = choices[0].get("message", {})
        raw = msg.get("content", "")

        return {
            "success": True,
            "llm_description": _build_llm_input(raw),
            "raw_response": raw,
            "error": None,
            "model_used": model,
        }

    def _error_result(self, error: str) -> Dict[str, Any]:
        """构建错误结果。"""
        return {
            "success": False,
            "llm_description": "",
            "raw_response": "",
            "error": error,
            "model_used": "",
        }


# ── BaseTool 适配器 ───────────────────────────────────────────────────────

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class VisionToolAdapter(BaseTool):
    """
    VisionTool 的 BaseTool 适配器。

    将 VisionTool 包装为符合 BaseTool 接口的工具，
    无需修改 VisionTool 原始代码。

    遵循适配器模式（Adapter Pattern），实现接口统一。
    """

    name = "vision_tool"
    description = (
        "多模态图片理解：截图直接发给 Qwen-VL，"
        "输出题目文字、LaTeX 公式、图形空间关系的结构化描述。"
    )
    version = "2.0.0"
    capabilities = [
        ToolCapability.IMAGE_RECOGNITION,
        ToolCapability.FORMULA_RECOGNITION,
    ]

    def __init__(self, vision_tool: VisionTool):
        """
        初始化适配器。

        Args:
            vision_tool: VisionTool 实例
        """
        self._vision_tool = vision_tool

    def get_info(self) -> Dict[str, Any]:
        """返回工具完整信息。"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": ToolInput.model_json_schema(),
            "api_configured": self._vision_tool.api_key_configured,
            "model": self._vision_tool._model,
        }

    def validate_input(self, input_data: ToolInput) -> Optional[str]:
        """验证输入数据。"""
        if not input_data.query.strip() and not input_data.parameters.get("image_source"):
            return "图片路径或 base64 数据不能为空"
        return None

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """
        执行图片识别（增强版异步实现）。

        使用 VisionTool 的异步流式识别方法，避免线程池开销。
        包含完整的日志记录和错误处理。
        """
        import time
        start_time = time.time()

        image_source = input_data.parameters.get("image_source", input_data.query)
        user_prompt = input_data.parameters.get("user_prompt")

        logger.info(
            f"VisionToolAdapter: 开始执行图片识别, "
            f"image_source类型={type(image_source).__name__}, "
            f"长度={len(str(image_source)) if image_source else 0}"
        )

        try:
            result = None
            async for event in self._vision_tool.recognize_stream(
                image_source=image_source,
                user_prompt=user_prompt,
            ):
                if event["type"] == "complete":
                    result = event
                    break
                elif event["type"] == "error":
                    raise RuntimeError(event["content"])

            elapsed_ms = (time.time() - start_time) * 1000

            if result and result.get("success"):
                logger.info(
                    f"VisionToolAdapter: 图片识别成功, "
                    f"模型={result.get('model_used', 'N/A')}, "
                    f"耗时={elapsed_ms:.1f}ms"
                )
                return ToolOutput(
                    success=True,
                    result=result.get("llm_description", ""),
                    tool_name=self.name,
                    execution_time_ms=elapsed_ms,
                    metadata={
                        "model_used": result.get("model_used", ""),
                        "raw_response": result.get("raw_response", ""),
                        "token_usage": result.get("token_usage"),
                    },
                )
            else:
                error_msg = result.get("content", "未知错误") if result else "无返回结果"
                logger.error(f"VisionToolAdapter: 图片识别失败: {error_msg}")
                return ToolOutput(
                    success=False,
                    error=f"图片识别失败: {error_msg}",
                    tool_name=self.name,
                    execution_time_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"VisionToolAdapter: 图片识别异常, "
                f"错误={error_msg}, 耗时={elapsed_ms:.1f}ms"
            )
            return ToolOutput(
                success=False,
                error=f"图片识别失败: {e}",
                tool_name=self.name,
                execution_time_ms=elapsed_ms,
            )
