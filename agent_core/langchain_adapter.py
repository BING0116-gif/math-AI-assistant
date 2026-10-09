"""
LangChain工具转换器 — 将自定义BaseTool转换为LangChain StructuredTool。

职责：
1. 将现有的BaseTool子类转换为LangChain可识别的工具格式
2. 保留自定义的工具能力标签(capabilities)等元数据
3. 统一错误处理和日志记录
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from contextvars import ContextVar, copy_context
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.execution_guard import ToolExecutionGuard, default_guard_policy
from tools.tool_ledger import (
    STATUS_ABORTED,
    STATUS_DENIED,
    STATUS_ERROR,
    STATUS_SUCCESS,
    begin_call,
    finish_call,
    record_tool_io,
    status_for_error_code as _status_for_error_code,
    summarize_parameters,
    summarize_result,
)

logger = logging.getLogger(__name__)


class LangChainToolConverter:
    """
    BaseTool → StructuredTool 转换器。

    将自定义工具生态系统无缝对接到LangChain Agent框架。

    Example:
        converter = LangChainToolConverter()
        lc_tools = converter.convert_batch([MathSolverTool(), VisionTool()])
        agent = create_react_agent(llm, lc_tools, prompt)
    """

    def __init__(self):
        self._conversion_cache: Dict[str, StructuredTool] = {}
        self._metadata_store: Dict[str, Dict[str, Any]] = {}
        # 转换器是进程级单例；请求上下文必须按异步任务隔离，避免并发会话互相
        # 覆盖 tutor_mode / user_id，造成模式门控绕过或学生数据串线。
        self._context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
            f"langchain_tool_context_{id(self)}",
            default=None,
        )
        self._execution_guard = ToolExecutionGuard(default_guard_policy())

    def set_context(self, context: Dict[str, Any]) -> None:
        """设置当前请求的上下文，工具执行时可读取其中的 user_id 等信息。"""
        self._context.set(context or {})

    def clear_context(self) -> None:
        """清除当前上下文。"""
        self._context.set(None)

    def _get_context(self) -> Dict[str, Any]:
        """返回当前异步任务绑定的请求上下文。"""
        return self._context.get() or {}

    @staticmethod
    def _tool_is_retryable(custom_tool: BaseTool) -> bool:
        """Only retry read/compute tools; never replay known write tools."""
        return ToolCapability.ERROR_BOOK_MANAGEMENT not in custom_tool.capabilities

    @staticmethod
    def _record_tool_status(tool_name: str, status: str) -> None:
        """Best-effort terminal status for mathai_agent_tool_calls_total."""
        try:
            from app.observability import AGENT_TOOL_CALLS

            AGENT_TOOL_CALLS.labels(tool_name[:80], status).inc()
        except Exception:
            pass

    @staticmethod
    def _terminal_status_for(error_code: str) -> str:
        """把 guard 错误码映射成展示用终态，与指标口径保持一致。"""
        return _status_for_error_code(error_code)

    def convert(self, custom_tool: BaseTool) -> StructuredTool:
        if custom_tool.name in self._conversion_cache:
            return self._conversion_cache[custom_tool.name]

        logger.info(f"转换工具: [{custom_tool.name}] v{custom_tool.version}")

        async def _execute_async(query: str, **kwargs) -> str:
            start_time = time.time()

            try:
                from app.services.mode_gating import is_tool_allowed, tool_denied_payload

                current_context = self._get_context()
                # 请求级列表由 ContextVar 隔离；可视化纯数据经它回传给 SSE，
                # 不混入 Markdown，也不会跨学生会话共享。
                current_context.setdefault("visualizations", [])
                current_context.setdefault("animations", [])
                # 工具调用台账同样按请求隔离，供时间线显示“调了哪个工具、是否成功”。
                begin_call(current_context, custom_tool.name, source="langchain_agent")
                mode = current_context.get("tutor_mode", "tutor_free")
                try:
                    allowed = is_tool_allowed(mode, custom_tool.name)
                except ValueError:
                    allowed = False
                capability_allowed = current_context.get("capability_allowed_tools")
                if capability_allowed is not None and custom_tool.name not in capability_allowed:
                    allowed = False
                if not allowed:
                    payload = tool_denied_payload(mode, custom_tool.name)
                    denials = current_context.setdefault("mode_tool_denials", [])
                    if payload not in denials:
                        denials.append(payload)
                    logger.warning(
                        "LangChain 模式工具调用被拒绝: mode=%s tool=%s code=%s",
                        payload["mode"],
                        custom_tool.name,
                        payload["code"],
                    )
                    finish_call(
                        current_context,
                        custom_tool.name,
                        STATUS_DENIED,
                        code=payload["code"],
                        elapsed_ms=(time.time() - start_time) * 1000,
                    )
                    # 拒绝分支不执行工具：参数里可能是题文，一律不记，只留稳定错误码。
                    record_tool_io(
                        current_context,
                        custom_tool.name,
                        output_summary=f"code={payload['code']}",
                    )
                    return "[MODE_TOOL_DENIED] " + json.dumps(payload, ensure_ascii=False)

                # 输入摘要只取白名单结构事实（类型/数量），不带 query 与题目文本；
                # 在执行前先登记，即使工具挂死或被取消，面板也能看出“它想做什么”。
                record_tool_io(
                    current_context,
                    custom_tool.name,
                    input_summary=summarize_parameters(kwargs),
                )

                input_data = ToolInput(
                    query=query,
                    parameters=kwargs,
                    context={
                        "source": "langchain_agent",
                        **current_context,  # ← 注入当前任务的 user_id 等上下文信息
                    },
                )

                try:
                    try:
                        from app.config.settings import settings
                        guard_enabled = settings.AGENT_TOOL_GUARD_ENABLED
                    except Exception:
                        guard_enabled = True
                    if guard_enabled:
                        result = await self._execution_guard.run(
                            custom_tool.name,
                            lambda: custom_tool.execute(input_data),
                            retryable=self._tool_is_retryable(custom_tool),
                        )
                    else:
                        result = await custom_tool.execute(input_data)
                except asyncio.CancelledError:
                    # 取消不是 Exception 派生的终态；不登记就会让时间线永远停在“进行中”。
                    finish_call(
                        current_context,
                        custom_tool.name,
                        STATUS_ABORTED,
                        code="TOOL_CANCELLED",
                        elapsed_ms=(time.time() - start_time) * 1000,
                    )
                    record_tool_io(
                        current_context,
                        custom_tool.name,
                        output_summary="code=TOOL_CANCELLED",
                    )
                    raise

                elapsed_ms = (time.time() - start_time) * 1000

                if result.success:
                    logger.info(
                        f"[{custom_tool.name}] 执行成功 "
                        f"({elapsed_ms:.1f}ms)"
                    )
                    self._record_tool_status(custom_tool.name, "success")
                    finish_call(
                        current_context,
                        custom_tool.name,
                        STATUS_SUCCESS,
                        elapsed_ms=elapsed_ms,
                    )
                    record_tool_io(
                        current_context,
                        custom_tool.name,
                        output_summary=summarize_result(result),
                    )
                    return str(result.result) if result.result else "执行成功"
                else:
                    # 终态指标单一漏斗：guard 归一化的 timeout/unavailable 在此可见；
                    # 策略层只记 started，避免把失败结果计成 success。
                    error_code = str((result.metadata or {}).get("error_code") or "TOOL_ERROR")
                    status = self._terminal_status_for(error_code)
                    self._record_tool_status(custom_tool.name, status)
                    logger.warning(
                        f"[{custom_tool.name}] 执行失败: {result.error}"
                    )
                    finish_call(
                        current_context,
                        custom_tool.name,
                        status,
                        code=error_code,
                        elapsed_ms=elapsed_ms,
                    )
                    # 失败只摘结果里的状态与错误码，不带 result.error 正文（可能含题文/堆栈）。
                    record_tool_io(
                        current_context,
                        custom_tool.name,
                        output_summary=summarize_result(result) or f"code={error_code}",
                    )
                    return f"[错误] {result.error}"

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"[{custom_tool.name}] 执行异常 ({elapsed_ms:.1f}ms): {e}\n"
                    f"{traceback.format_exc()}"
                )
                finish_call(
                    self._get_context(),
                    custom_tool.name,
                    STATUS_ERROR,
                    code="TOOL_EXCEPTION",
                    elapsed_ms=elapsed_ms,
                )
                record_tool_io(
                    self._get_context(),
                    custom_tool.name,
                    output_summary="code=TOOL_EXCEPTION",
                )
                return f"[异常] {type(e).__name__}: {str(e)}"

        def _execute_sync(query: str, **kwargs) -> str:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    context = copy_context()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            context.run,
                            asyncio.run,
                            _execute_async(query, **kwargs),
                        )
                        return future.result(timeout=30)
                else:
                    return loop.run_until_complete(_execute_async(query, **kwargs))
            except Exception as e:
                return f"[同步执行错误] {e}"

        description = self._build_langchain_description(custom_tool)

        lc_tool = StructuredTool.from_function(
            coroutine=_execute_async,
            func=_execute_sync,
            name=custom_tool.name,
            description=description,
            args_schema=self._create_args_schema(custom_tool),
        )

        self._conversion_cache[custom_tool.name] = lc_tool

        self._metadata_store[custom_tool.name] = {
            'capabilities': [cap.value for cap in custom_tool.capabilities],
            'version': custom_tool.version,
            'original_tool': custom_tool,
            'converted_at': time.time(),
        }

        return lc_tool

    def convert_batch(self, tools: List[BaseTool]) -> List[StructuredTool]:
        return [self.convert(tool) for tool in tools]

    def get_metadata(self, tool_name: str) -> Optional[Dict[str, Any]]:
        return self._metadata_store.get(tool_name)

    def get_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._metadata_store)

    def clear_cache(self):
        self._conversion_cache.clear()
        self._metadata_store.clear()
        logger.info("工具转换缓存已清除")

    def _build_langchain_description(self, tool: BaseTool) -> str:
        caps = ", ".join(cap.value for cap in tool.capabilities)

        description_parts = [
            f"{tool.description}",
            f"\n能力标签: {caps}",
            f"版本: {tool.version}",
        ]

        capability_hints = {
            ToolCapability.SYMBOLIC_COMPUTATION: "\n适用于: 符号计算、公式推导、方程求解",
            ToolCapability.NUMERICAL_COMPUTATION: "\n适用于: 数值计算、近似求解、绘图",
            ToolCapability.IMAGE_RECOGNITION: "\n适用于: 图片内容识别、OCR、公式识别",
            ToolCapability.FORMULA_RECOGNITION: "\n适用于: 数学公式识别和LaTeX转换",
            ToolCapability.PLOTTING: "\n适用于: 函数图像绘制、可视化",
            ToolCapability.PRACTICE_GENERATION: "\n适用于: 生成练习题、变式训练",
            ToolCapability.KNOWLEDGE_RETRIEVAL: "\n适用于: 知识点检索、定理查询",
            ToolCapability.VERIFICATION: "\n适用于: 答案验证、步骤检查",
            ToolCapability.ERROR_BOOK_MANAGEMENT: "\n适用于: 错题本管理、错题分析",
        }

        for cap in tool.capabilities:
            if cap in capability_hints:
                description_parts.append(capability_hints[cap])

        return "\n".join(description_parts)

    def _create_args_schema(self, tool: BaseTool) -> type[BaseModel]:
        custom_schema = getattr(tool, "args_schema", None)
        if isinstance(custom_schema, type) and issubclass(custom_schema, BaseModel):
            return custom_schema
        fields = {
            'query': (
                str,
                Field(..., description="用户问题或待处理的文本内容"),
            ),
            'parameters': (
                Optional[Dict[str, Any]],
                Field(
                    default_factory=dict,
                    description="可选的额外参数（如图像路径、计算选项等）",
                ),
            ),
        }

        return create_model(
            f'{tool.name.title()}Args',
            __base__=BaseModel,
            **fields,
        )


_converter_instance: Optional[LangChainToolConverter] = None


def get_tool_converter() -> LangChainToolConverter:
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = LangChainToolConverter()
    return _converter_instance


def convert_tools_to_langchain(tools: List[BaseTool]) -> List[StructuredTool]:
    """
    便捷函数：批量转换工具。

    Example:
        from agent_core.langchain_adapter import convert_tools_to_langchain

        lc_tools = convert_tools_to_langchain(registry.get_all_tools())
    """
    return get_tool_converter().convert_batch(tools)
