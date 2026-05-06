"""
ToolInvoker — 工具调用执行器。

提供工具的安全调用、参数解析、结果格式化等能力，
作为 Agent 与 ToolRegistry 之间的桥梁。
"""

from __future__ import annotations

import json
import logging
import time
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from tools.base_tool import BaseTool, ToolInput, ToolOutput
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolInvokeError(Exception):
    """工具调用错误。"""

    def __init__(self, tool_name: str, message: str, recoverable: bool = True):
        self.tool_name = tool_name
        self.recoverable = recoverable
        super().__init__(f"[{tool_name}] {message}")


class ToolInvoker:
    """
    工具调用执行器。

    核心职责：
    1. 解析 Agent 生成的工具调用指令
    2. 验证和格式化工具参数
    3. 执行工具调用并处理结果
    4. 错误处理与重试机制
    5. 执行统计与日志记录

    Example:
        invoker = ToolInvoker(registry)
        result = await invoker.invoke("math_solver", {"query": "求∫x²dx"})
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_retries: int = 1,
        timeout_seconds: float = 30.0,
    ):
        self._registry = registry
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds

    @property
    def registry(self) -> ToolRegistry:
        """获取工具注册表。"""
        return self._registry

    def parse_action_input(self, action_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        解析 Action Input 文本，提取工具名和参数。

        支持多种格式：
        - JSON: {"query": "...", "parameters": {...}}
        - 纯文本: "用户问题"

        Args:
            action_text: Agent 返回的 Action Input 文本。

        Returns:
            (工具名称, 参数字典) 元组。

        Raises:
            ToolInvokeError: 解析失败时抛出。
        """
        action_text = action_text.strip()

        if not action_text:
            raise ToolInvokeError("", "Action Input 为空", recoverable=False)

        try:
            parsed = json.loads(action_text)
            if isinstance(parsed, dict):
                return self._extract_from_dict(parsed)
            raise ToolInvokeError("", f"无法理解的 JSON 结构: {action_text}", recoverable=False)
        except json.JSONDecodeError:
            return self._parse_text_format(action_text)

    def _extract_from_dict(self, data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """从字典中提取工具名和参数。"""
        query = data.get("query", data.get("question", data.get("text", "")))
        parameters = data.get("parameters", data.get("params", {}))
        tool_name = data.get("tool", data.get("tool_name", ""))

        if not query and not parameters:
            query = str(data)

        return tool_name, {"query": query, "parameters": parameters}

    def _parse_text_format(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """
        从纯文本中提取参数。

        策略：直接作为 query 处理。
        """
        return "", {"query": text, "parameters": {}}

    def _parse_tool_call_line(self, line: str) -> Optional[Tuple[str, str]]:
        """
        解析工具调用行。

        支持格式：
        - "Action: tool_name"
        - "Action: tool_name(input)"
        - "tool_name: ..."

        Returns:
            (tool_name, remaining) 元组。
        """
        line = line.strip()

        patterns = [
            r"^Action:\s*(\w+)\s*(.*)$",
            r"^(\w+):\s*(.*)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                tool_name = groups[0].strip()
                remaining = groups[1].strip() if len(groups) > 1 else ""
                return tool_name, remaining

        return None

    def extract_tool_call(self, agent_output: str) -> Optional[Dict[str, str]]:
        """
        从 Agent 输出中提取工具调用信息。

        解析格式：
        Action: tool_name
        Action Input: {...}

        Args:
            agent_output: Agent 输出的原始文本。

        Returns:
            {"tool": tool_name, "input": action_input} 或 None。
        """
        lines = agent_output.strip().split("\n")
        tool_name = ""
        action_input = ""

        for line in lines:
            line = line.strip()
            if line.startswith("Action:"):
                parsed = self._parse_tool_call_line(line)
                if parsed:
                    tool_name = parsed[0]
            elif line.startswith("Action Input:"):
                action_input = line[len("Action Input:"):].strip()

        if tool_name and tool_name.lower() != "final answer":
            return {"tool": tool_name, "input": action_input}

        return None

    async def invoke(
        self,
        tool_name: str,
        input_data: ToolInput,
        retry: bool = True,
    ) -> ToolOutput:
        """
        执行工具调用。

        Args:
            tool_name: 工具名称。
            input_data: 工具输入数据。
            retry: 是否允许重试。

        Returns:
            ToolOutput 标准化结果。
        """
        execution_id = str(uuid.uuid4())[:8]
        logger.info(
            f"[{execution_id}] ToolInvoker.invoke: [{tool_name}] "
            f"query={input_data.query[:50]!r}..."
        )

        last_error = None
        attempts = self._max_retries + 1 if retry else 1

        for attempt in range(attempts):
            try:
                result = await self._registry.execute_safe(tool_name, input_data)

                if result.success:
                    logger.info(
                        f"[{execution_id}] 工具调用成功: [{tool_name}] "
                        f"耗时={result.execution_time_ms:.1f}ms"
                    )
                    return result

                last_error = result.error
                logger.warning(
                    f"[{execution_id}] 工具调用失败 (attempt {attempt + 1}): "
                    f"[{tool_name}] {last_error}"
                )

                if attempt < attempts - 1 and result.success is None:
                    continue
                break

            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                logger.error(
                    f"[{execution_id}] 工具调用异常 (attempt {attempt + 1}): "
                    f"[{tool_name}] {last_error}"
                )

        return ToolOutput(
            success=False,
            error=f"工具调用失败: {last_error}",
            tool_name=tool_name,
            execution_time_ms=0.0,
        )

    def format_result_for_llm(self, result: ToolOutput) -> str:
        """
        将工具执行结果格式化为 LLM 可理解的形式。

        Args:
            result: 工具执行结果。

        Returns:
            格式化后的结果文本。
        """
        if result.success:
            output = result.result
            if isinstance(output, dict):
                return json.dumps(output, ensure_ascii=False, indent=2)
            if output is None:
                return "(无返回值)"
            return str(output)

        return f"【错误】{result.error}"

    async def invoke_from_text(
        self,
        action_text: str,
        session_id: str = "default",
    ) -> Tuple[bool, str]:
        """
        从文本直接调用工具（自动解析工具名和参数）。

        Args:
            action_text: 包含工具名和参数的文本。
            session_id: 会话 ID（用于上下文）。

        Returns:
            (success, result_or_error) 元组。
        """
        parsed = self.extract_tool_call(action_text)
        if not parsed:
            return False, "无法从文本中提取工具调用信息"

        tool_name = parsed["tool"]
        action_input = parsed["input"]

        if not self._registry.has_tool(tool_name):
            return False, f"工具未注册: '{tool_name}'"

        try:
            tool_name, params = self.parse_action_input(action_input)

            if tool_name and self._registry.has_tool(tool_name):
                final_tool = tool_name
            else:
                final_tool = parsed["tool"]

            input_data = ToolInput(
                query=params.get("query", action_input),
                parameters=params.get("parameters", {}),
                context={"session_id": session_id},
            )

            result = await self.invoke(final_tool, input_data, retry=False)
            return result.success, self.format_result_for_llm(result)

        except ToolInvokeError as e:
            return False, str(e)
        except Exception as e:
            return False, f"工具调用异常: {e}"
