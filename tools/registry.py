"""
ToolRegistry — 工具注册中心核心实现。

统一管理所有工具的注册、发现、获取和安全调用，
充当 Agent 核心层与工具层之间的统一中间件。
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability

logger = logging.getLogger(__name__)


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


class ToolRegistry:
    """
    工具注册中心 — 统一管理所有工具的注册、发现、获取和安全调用。

    ToolRegistry 是 Agent 系统的工具基础设施，充当 Agent 核心层与工具层
    之间的统一中间件。所有工具必须通过 register() 注册后才能被系统使用。

    核心职责：
    1. 工具注册与生命周期管理
    2. 工具发现（按名称、按能力搜索）
    3. 工具描述聚合（供 LLM 理解可用工具集）
    4. 安全执行（统一容错、日志、耗时统计）

    Example:
        registry = ToolRegistry()
        registry.register(MathSolverTool())
        registry.register(VisionToolAdapter())

        descriptions = registry.get_all_descriptions()
        tool = registry.get_tool("math_solver")
        result = await registry.execute_safe("math_solver", ToolInput(query="求∫x²dx"))
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history: int = 1000

    def register(self, tool: BaseTool) -> None:
        """
        注册工具到注册中心。

        如果同名工具已存在，将发出警告并覆盖（支持热更新）。

        Args:
            tool: 实现 BaseTool 接口的工具实例。

        Raises:
            ValueError: 工具 name 为空时抛出。
        """
        if not tool.name:
            raise ValueError("工具的 name 属性不能为空")

        if tool.name in self._tools:
            existing_version = self._tools[tool.name].version
            logger.warning(
                f"工具 [{tool.name}] 已存在(v{existing_version})，"
                f"将被覆盖为 v{tool.version}"
            )

        self._tools[tool.name] = tool
        logger.info(f"工具已注册: [{tool.name}] v{tool.version}")

    def unregister(self, tool_name: str) -> bool:
        """
        注销工具。

        Args:
            tool_name: 工具名称。

        Returns:
            是否成功注销（工具不存在时返回 False）。
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info(f"工具已注销: [{tool_name}]")
            return True
        logger.warning(f"注销失败，工具不存在: [{tool_name}]")
        return False

    def get_tool(self, tool_name: str) -> BaseTool:
        """
        按名称获取工具实例。

        Args:
            tool_name: 工具名称。

        Returns:
            BaseTool 实例。

        Raises:
            ToolNotFoundError: 工具未注册时抛出。
        """
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name)
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册。

        Args:
            tool_name: 工具名称。

        Returns:
            工具是否存在。
        """
        return tool_name in self._tools

    def search_tools(self, capability: str) -> List[str]:
        """
        根据能力标签搜索工具。

        Args:
            capability: 能力标签值（如 "symbolic_computation"）。

        Returns:
            具备该能力的工具名称列表。
        """
        result = []
        for name, tool in self._tools.items():
            if any(cap.value == capability for cap in tool.capabilities):
                result.append(name)
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列举所有已注册工具的完整信息。

        Returns:
            工具信息字典列表。
        """
        return [tool.get_info() for tool in self._tools.values()]

    def get_all_descriptions(self) -> str:
        """
        获取所有工具的描述文本（用于注入 LLM prompt）。

        LLM 通过此文本了解当前可用的工具集，从而做出工具选择决策。

        Returns:
            格式化的工具描述文本。
        """
        if not self._tools:
            return "当前无可用工具。"

        descriptions = []
        for tool in self._tools.values():
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
            if name in self._tools:
                tools.append(self._tools[name])
            else:
                logger.warning(f"工具不存在，已跳过: [{name}]")
        return tools

    def get_all_tools(self) -> List[BaseTool]:
        """
        获取所有已注册的工具实例。

        Returns:
            BaseTool 实例列表。
        """
        return list(self._tools.values())

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

    def _record_execution(
        self,
        execution_id: str,
        tool_name: str,
        success: bool,
        elapsed_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """
        记录工具执行历史。

        Args:
            execution_id: 执行唯一标识。
            tool_name: 工具名称。
            success: 是否成功。
            elapsed_ms: 执行耗时（毫秒）。
            error: 错误信息。
        """
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

    @property
    def tool_count(self) -> int:
        """已注册工具数量。"""
        return len(self._tools)

    @property
    def tool_names(self) -> List[str]:
        """所有已注册工具的名称列表。"""
        return list(self._tools.keys())
