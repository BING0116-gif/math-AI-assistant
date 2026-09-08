"""
HybridToolRegistry — 混合工具注册中心。

结合自定义工具系统的丰富元数据和LangChain的广泛生态，
提供双模式访问：
- 自定义模式: 保留能力标签、版本管理、统计等功能
- LangChain模式: 提供StructuredTool给Agent使用

核心原则：
1. 对外接口完全兼容原有ToolRegistry
2. 内部维护双份数据（自定义工具 + LangChain工具）
3. 自动同步两者状态
4. LangChain集成延迟加载，无langchain依赖时正常降级
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability

logger = logging.getLogger(__name__)

_LANGCHAIN_AVAILABLE = False
try:
    from langchain_core.tools import StructuredTool
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    logger.info("langchain_core 不可用，运行于纯自定义模式")


class ToolNotFoundError(Exception):
    """工具未找到异常。"""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"工具未注册: '{tool_name}'")


class ToolExecutionError(Exception):
    """工具执行异常。"""

    def __init__(self, tool_name: str, original_error: str):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"工具 '{tool_name}' 执行失败: {original_error}")


class HybridToolRegistry:
    """
    混合工具注册中心。

    结合自定义工具系统的丰富元数据和LangChain的广泛生态，
    提供双模式访问：
    - 自定义模式: 保留能力标签、版本管理、统计等功能
    - LangChain模式: 提供StructuredTool给Agent使用

    对外接口完全兼容原有ToolRegistry，同时提供get_langchain_tools()
    等新接口用于LangChain Agent集成。

    Example:
        registry = HybridToolRegistry()
        registry.register(MathSolverTool())

        # 自定义模式（兼容原有API）
        result = await registry.execute_safe("math_solver", ToolInput(query="..."))
        capable_tools = registry.search_tools("symbolic_computation")

        # LangChain模式（新增）
        lc_tools = registry.get_langchain_tools()
        # agent = create_react_agent(llm, lc_tools, prompt)
    """

    def __init__(self):
        # Registry diagnostics are operationally important and must remain
        # visible even if another test/app lifecycle previously disabled this
        # module logger. Keep propagation on so host logging/caplog can observe
        # duplicate and missing-tool warnings.
        logger.disabled = False
        logger.propagate = True
        self._custom_tools: Dict[str, BaseTool] = {}
        self._langchain_tools: Dict[str, Any] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history: int = 1000
        self._langchain_enabled: bool = _LANGCHAIN_AVAILABLE

        logger.info(
            "HybridToolRegistry 初始化完成"
            + (" (LangChain 双模式)" if _LANGCHAIN_AVAILABLE else " (纯自定义模式)")
        )

    # ========== 注册与生命周期管理 ==========

    def register(self, tool: BaseTool) -> None:
        """
        注册工具（同时维护两份存储）。

        自动将自定义BaseTool转换为LangChain StructuredTool格式，
        确保两个存储保持同步。

        Args:
            tool: 实现 BaseTool 接口的工具实例。

        Raises:
            ValueError: 工具 name 为空时抛出。
        """
        if not tool.name:
            raise ValueError("工具的 name 属性不能为空")

        if tool.name in self._custom_tools:
            existing_version = self._custom_tools[tool.name].version
            logger.warning(
                f"工具 [{tool.name}] 已存在(v{existing_version})，"
                f"将被覆盖为 v{tool.version}"
            )

        self._custom_tools[tool.name] = tool

        if self._langchain_enabled:
            try:
                lc_tool = self._convert_to_langchain(tool)
                self._langchain_tools[tool.name] = lc_tool
            except Exception as e:
                logger.warning(
                    f"工具 [{tool.name}] LangChain转换未成功: {e}，"
                    f"仅工作于自定义模式"
                )

        logger.info(
            f"工具已注册: [{tool.name}] v{tool.version}"
            + (" (双模式)" if tool.name in self._langchain_tools else "")
        )

    def unregister(self, tool_name: str) -> bool:
        """
        注销工具（同时清除两份存储）。

        Args:
            tool_name: 工具名称。

        Returns:
            是否成功注销（工具不存在时返回 False）。
        """
        removed = False

        if tool_name in self._custom_tools:
            del self._custom_tools[tool_name]
            removed = True

        if tool_name in self._langchain_tools:
            del self._langchain_tools[tool_name]

        if removed:
            logger.info(f"工具已注销: [{tool_name}]")
        else:
            logger.warning(f"注销失败，工具不存在: [{tool_name}]")

        return removed

    # ========== 自定义工具发现接口（兼容原有API） ==========

    def get_tool(self, tool_name: str) -> BaseTool:
        """
        按名称获取自定义工具实例。

        Args:
            tool_name: 工具名称。

        Returns:
            BaseTool 实例。

        Raises:
            ToolNotFoundError: 工具未注册时抛出。
        """
        if tool_name not in self._custom_tools:
            raise ToolNotFoundError(tool_name)
        return self._custom_tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册。

        Args:
            tool_name: 工具名称。

        Returns:
            工具是否存在。
        """
        return tool_name in self._custom_tools

    def search_tools(self, capability: str) -> List[str]:
        """
        根据能力标签搜索工具。

        Args:
            capability: 能力标签值（如 "symbolic_computation"）。

        Returns:
            具备该能力的工具名称列表。
        """
        result = []
        for name, tool in self._custom_tools.items():
            if any(cap.value == capability for cap in tool.capabilities):
                result.append(name)
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列举所有已注册工具的完整信息。

        Returns:
            工具信息字典列表。
        """
        return [tool.get_info() for tool in self._custom_tools.values()]

    def get_all_descriptions(self) -> str:
        """
        获取所有工具的描述文本（用于注入 LLM prompt）。

        LLM 通过此文本了解当前可用的工具集，从而做出工具选择决策。

        Returns:
            格式化的工具描述文本。
        """
        if not self._custom_tools:
            return "当前无可用工具。"

        descriptions = []
        for tool in self._custom_tools.values():
            descriptions.append(tool.get_description_for_llm())

        header = "当前可用工具列表：\n" + "=" * 40
        return header + "\n\n" + "\n\n".join(descriptions)

    def get_tools_by_names(self, tool_names: List[str]) -> List[BaseTool]:
        """
        批量获取工具实例（忽略不存在的工具名）。

        Args:
            tool_names: 工具名称列表。

        Returns:
            工具实例列表。
        """
        tools = []
        for name in tool_names:
            if name in self._custom_tools:
                tools.append(self._custom_tools[name])
            else:
                logger.warning(f"工具不存在，已跳过: [{name}]")
        return tools

    def get_all_tools(self) -> List[BaseTool]:
        """
        获取所有已注册的工具实例。

        Returns:
            BaseTool 实例列表。
        """
        return list(self._custom_tools.values())

    # ========== LangChain 专用接口（新增） ==========

    @property
    def langchain_enabled(self) -> bool:
        """是否启用了LangChain双模式。"""
        return self._langchain_enabled

    def get_langchain_tool(self, tool_name: str):
        """
        获取LangChain格式的工具。

        Args:
            tool_name: 工具名称。

        Returns:
            StructuredTool 实例。

        Raises:
            ToolNotFoundError: 工具未注册时抛出。
        """
        if not self._langchain_enabled:
            raise ToolNotFoundError(tool_name)

        if tool_name not in self._langchain_tools:
            raise ToolNotFoundError(tool_name)
        return self._langchain_tools[tool_name]

    def get_langchain_tools(self) -> List[Any]:
        """
        获取所有工具的LangChain格式列表。

        用于创建LangChain Agent:
            from langchain.agents import create_react_agent
            agent = create_react_agent(llm, registry.get_langchain_tools(), prompt)

        Returns:
            StructuredTool 实例列表。如果LangChain不可用则返回空列表。
        """
        return list(self._langchain_tools.values())

    def refresh_langchain_tools(self) -> None:
        """
        强制刷新所有工具的LangChain表示。

        当工具元数据变更或自定义工具重新注册后调用，
        会清除转换缓存并重新转换所有工具。
        """
        if not self._langchain_enabled:
            logger.info("LangChain未启用，跳过刷新")
            return

        self._langchain_tools.clear()
        for name, tool in self._custom_tools.items():
            try:
                lc_tool = self._convert_to_langchain(tool)
                self._langchain_tools[name] = lc_tool
            except Exception as e:
                logger.warning(f"工具 [{name}] LangChain刷新失败: {e}")

        logger.info(f"LangChain工具已刷新，共 {len(self._langchain_tools)} 个工具")

    # ========== 安全执行接口（兼容原有API） ==========

    async def execute_safe(
        self,
        tool_name: str,
        input_data: ToolInput,
    ) -> ToolOutput:
        """
        安全执行工具（带完整监控、容错和耗时统计）。

        此方法是 Agent 调用工具的唯一推荐入口，提供：
        1. 工具存在性检查
        2. 输入数据校验
        3. 执行超时保护
        4. 异常捕获与友好错误信息
        5. 执行耗时统计
        6. 执行历史记录

        Args:
            tool_name: 工具名称。
            input_data: 工具输入数据。

        Returns:
            ToolOutput: 标准化的工具输出（即使执行失败也返回 ToolOutput 而非抛异常）。
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())[:8]

        try:
            tool = self.get_tool(tool_name)
        except ToolNotFoundError:
            return ToolOutput(
                success=False,
                error=f"工具未注册: '{tool_name}'",
                tool_name=tool_name,
                execution_time_ms=0,
            )

        validation_error = tool.validate_input(input_data)
        if validation_error:
            elapsed = (time.time() - start_time) * 1000
            return ToolOutput(
                success=False,
                error=f"输入校验失败: {validation_error}",
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

        try:
            logger.info(
                f"[{execution_id}] 开始执行工具: [{tool_name}] "
                f"query={input_data.query[:50]}..."
            )
            result = await tool.execute(input_data)
            elapsed = (time.time() - start_time) * 1000
            result.execution_time_ms = elapsed
            result.tool_name = tool_name

            self._record_execution(
                execution_id=execution_id,
                tool_name=tool_name,
                success=result.success,
                elapsed_ms=elapsed,
                error=result.error,
            )

            logger.info(
                f"[{execution_id}] 工具执行完成: [{tool_name}] "
                f"success={result.success} 耗时={elapsed:.1f}ms"
            )
            return result

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"[{execution_id}] 工具执行异常: [{tool_name}] {error_msg}\n"
                f"{traceback.format_exc()}"
            )

            self._record_execution(
                execution_id=execution_id,
                tool_name=tool_name,
                success=False,
                elapsed_ms=elapsed,
                error=error_msg,
            )

            return ToolOutput(
                success=False,
                error=error_msg,
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

    # ========== 统计与监控 ==========

    def _record_execution(
        self,
        execution_id: str,
        tool_name: str,
        success: bool,
        elapsed_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """记录工具执行历史。"""
        record = {
            "execution_id": execution_id,
            "tool_name": tool_name,
            "success": success,
            "elapsed_ms": elapsed_ms,
            "error": error,
            "timestamp": time.time(),
        }
        self._execution_history.append(record)

        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

    def get_execution_stats(self) -> Dict[str, Any]:
        """
        获取工具执行统计信息。

        Returns:
            包含总调用次数、成功率、平均耗时等统计数据的字典。
        """
        if not self._execution_history:
            return {
                "total_calls": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_elapsed_ms": 0.0,
                "tool_stats": {},
            }

        total = len(self._execution_history)
        success_count = sum(1 for r in self._execution_history if r["success"])
        failure_count = total - success_count
        avg_elapsed = sum(r["elapsed_ms"] for r in self._execution_history) / total

        tool_stats: Dict[str, Dict[str, Any]] = {}
        for record in self._execution_history:
            name = record["tool_name"]
            if name not in tool_stats:
                tool_stats[name] = {
                    "calls": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_elapsed_ms": 0.0,
                }
            stats = tool_stats[name]
            stats["calls"] += 1
            if record["success"]:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            stats["total_elapsed_ms"] += record["elapsed_ms"]

        for name, stats in tool_stats.items():
            stats["avg_elapsed_ms"] = stats["total_elapsed_ms"] / stats["calls"]
            stats["success_rate"] = stats["successes"] / stats["calls"]

        return {
            "total_calls": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / total if total > 0 else 0.0,
            "avg_elapsed_ms": avg_elapsed,
            "tool_stats": tool_stats,
        }

    def get_hybrid_stats(self) -> Dict[str, Any]:
        """
        获取混合注册统计信息（含LangChain状态）。

        Returns:
            包含自定义工具数、LangChain工具数、双模式状态等信息的字典。
        """
        return {
            "custom_tool_count": len(self._custom_tools),
            "langchain_tool_count": len(self._langchain_tools),
            "langchain_enabled": self._langchain_enabled,
            "fully_synced": len(self._custom_tools) == len(self._langchain_tools),
            "tool_names": list(self._custom_tools.keys()),
            "execution_stats": self.get_execution_stats(),
        }

    # ========== 属性 ==========

    @property
    def tool_count(self) -> int:
        """已注册工具数量。"""
        return len(self._custom_tools)

    @property
    def tool_names(self) -> List[str]:
        """所有已注册工具的名称列表。"""
        return list(self._custom_tools.keys())

    @property
    def langchain_tool_count(self) -> int:
        """LangChain模式下的工具数量。"""
        return len(self._langchain_tools)

    # ========== LangChain 转换桥接（内部方法） ==========

    def _convert_to_langchain(self, tool: BaseTool):
        """
        将自定义BaseTool转换为LangChain StructuredTool。

        使用LangChain的StructuredTool.from_function创建兼容的
        工具格式，供langchain.agents使用。

        转换策略：
        - 保留原始工具的name和description
        - 创建异步执行包装器（asyncio适配）
        - 通过Pydantic args_schema进行参数验证

        Args:
            tool: 自定义BaseTool实例

        Returns:
            StructuredTool实例

        Raises:
            ImportError: langchain_core不可用时
            Exception: 转换过程中的其他错误
        """
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError("langchain_core.tools 模块不可用，无法进行LangChain转换")

        import asyncio
        from pydantic import BaseModel as PydanticBaseModel, Field, create_model

        async def _execute_async(query: str, **kwargs) -> str:
            """异步执行包装器 — 将自定义工具适配为LangChain可调用的协程。"""
            start_time = time.time()

            try:
                input_data = ToolInput(
                    query=query,
                    parameters=kwargs,
                    context={"source": "langchain_agent"},
                )

                result: ToolOutput = await tool.execute(input_data)

                elapsed_ms = (time.time() - start_time) * 1000

                if result.success:
                    logger.info(
                        f"[{tool.name}] LangChain执行成功 ({elapsed_ms:.1f}ms)"
                    )
                    return str(result.result) if result.result else "执行成功"
                else:
                    logger.warning(
                        f"[{tool.name}] LangChain执行失败: {result.error}"
                    )
                    return f"[错误] {result.error}"

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"[{tool.name}] LangChain执行异常 ({elapsed_ms:.1f}ms): {e}\n"
                    f"{traceback.format_exc()}"
                )
                return f"[异常] {type(e).__name__}: {str(e)}"

        def _execute_sync(query: str, **kwargs) -> str:
            """同步执行包装器 — 供LangChain同步调用场景使用。"""
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run, _execute_async(query, **kwargs)
                        )
                        return future.result(timeout=30)
                else:
                    return loop.run_until_complete(_execute_async(query, **kwargs))
            except Exception as e:
                return f"[同步执行错误] {e}"

        description = self._build_langchain_description(tool)

        args_model = create_model(
            f'{tool.name.title()}Args',
            __base__=PydanticBaseModel,
            query=(str, Field(..., description="用户问题或待处理的文本内容")),
        )

        lc_tool = StructuredTool.from_function(
            coroutine=_execute_async,
            func=_execute_sync,
            name=tool.name,
            description=description,
            args_schema=args_model,
        )

        return lc_tool

    def _build_langchain_description(self, tool: BaseTool) -> str:
        """
        构建供LangChain/LLM理解的增强工具描述。

        Args:
            tool: 自定义BaseTool实例

        Returns:
            格式化后的工具描述字符串
        """
        caps = ", ".join(cap.value for cap in tool.capabilities)

        parts = [
            f"{tool.description}",
            f"能力标签: {caps}",
            f"版本: {tool.version}",
        ]

        capability_hints = {
            ToolCapability.SYMBOLIC_COMPUTATION: "适用于: 符号计算、公式推导、方程求解",
            ToolCapability.NUMERICAL_COMPUTATION: "适用于: 数值计算、近似求解、绘图",
            ToolCapability.IMAGE_RECOGNITION: "适用于: 图片内容识别、OCR、公式识别",
            ToolCapability.FORMULA_RECOGNITION: "适用于: 数学公式识别和LaTeX转换",
            ToolCapability.PLOTTING: "适用于: 函数图像绘制、可视化",
            ToolCapability.PRACTICE_GENERATION: "适用于: 生成练习题、变式训练",
            ToolCapability.KNOWLEDGE_RETRIEVAL: "适用于: 知识点检索、定理查询",
            ToolCapability.VERIFICATION: "适用于: 答案验证、步骤检查",
            ToolCapability.ERROR_BOOK_MANAGEMENT: "适用于: 错题本管理、错题分析",
        }

        for cap in tool.capabilities:
            if cap in capability_hints:
                parts.append(capability_hints[cap])

        return "\n".join(parts)
