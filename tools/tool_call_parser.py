"""
ToolCallParser — 统一的工具调用解析器。

整合了 react.py 的 _detect_tool_call 和 tool_invoker.py 的 parse_action_input
中的重复解析逻辑，提供一致的多格式工具调用解析能力。

支持格式：
- 正则模式: Action: tool_name 或 工具: tool_name
- JSON: {"tool": "...", "query": "...", "parameters": {...}}
- 纯文本: 直接匹配工具名
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 正则模式（预编译提升性能）
_REGEX_PATTERNS = [
    re.compile(r"Action:\s*(\w+)"),
    re.compile(r"使用?工具[：:]\s*(\w+)"),
]

# 终止词（不应触发工具调用）
_STOP_WORDS = frozenset({
    "final", "final answer", "finish", "none", "答案", "结束", "",
})

# JSON 提取正则
_JSON_PATTERN = re.compile(r"\{[^{}]*\}")


@dataclass
class ToolCall:
    """解析后的工具调用信息。"""

    tool_name: str
    action_input: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    format_type: str = "unknown"  # "regex" | "json" | "text"


class ToolCallParser:
    """
    统一的工具调用解析器。

    整合了 ReActStrategy._detect_tool_call 和 ToolInvoker.parse_action_input
    的解析逻辑，按优先级尝试多种格式：JSON → 正则模式 → 纯文本。

    Example:
        parser = ToolCallParser(available_tools={"math_solver", "vision_tool"})

        # 正则模式
        result = parser.parse('Action: math_solver\\nAction Input: {"query": "求∫x²dx"}')

        # JSON 格式
        result = parser.parse('{"tool": "vision_tool", "query": "识别图片"}')
    """

    def __init__(self, available_tools: Optional[Set[str]] = None):
        """
        Args:
            available_tools: 可用工具名称集合，用于验证工具名有效性。
                             为 None 时不验证。
        """
        self._available_tools = available_tools

    def update_available_tools(self, tools: Set[str]) -> None:
        """更新可用工具列表。"""
        self._available_tools = tools

    def parse(self, text: str) -> Optional[ToolCall]:
        """
        解析文本中的工具调用（自动检测格式）。

        优先级：JSON > 正则模式 > 纯文本

        Args:
            text: 待解析的文本。

        Returns:
            ToolCall 对象，未检测到工具调用时返回 None。
        """
        text = text.strip()
        if not text or len(text) < 5:
            return None

        # 1. 尝试 JSON 格式
        result = self._try_parse_json(text)
        if result:
            return result

        # 2. 尝试正则模式
        result = self._try_parse_regex(text)
        if result:
            return result

        # 3. 纯文本兜底
        return self._try_parse_text(text)

    def parse_action_input(self, action_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        解析 Action Input 文本，提取工具名和参数。
        兼容旧的 ToolInvoker.parse_action_input 接口。

        策略：
        1. 先尝试 parse() 找到完整的工具调用信息
        2. 如果 parse() 返回 None，尝试直接解析 JSON dict（无 tool_name 的纯 JSON）
        3. 否则作为纯文本 query 处理

        Args:
            action_text: Agent 返回的 Action Input 文本。

        Returns:
            (工具名称, 参数字典) 元组。
        """
        result = self.parse(action_text)
        if result:
            return result.tool_name, result.parameters

        # 兜底：尝试直接解析 JSON dict（无 tool_name 字段的情况）
        try:
            parsed = json.loads(action_text)
            if isinstance(parsed, dict):
                query = parsed.get("query", parsed.get("question", parsed.get("text", "")))
                parameters = parsed.get("parameters", parsed.get("params", {}))
                tool_name = parsed.get("tool", parsed.get("tool_name", ""))
                if not query and not parameters:
                    query = str(parsed)
                return tool_name, {"query": query, "parameters": parameters}
        except (json.JSONDecodeError, ValueError):
            pass

        return "", {"query": action_text, "parameters": {}}

    # ── 内部解析方法 ──

    def _try_parse_json(self, text: str) -> Optional[ToolCall]:
        """尝试解析 JSON 格式的工具调用。"""
        match = _JSON_PATTERN.search(text)
        if not match:
            return None

        try:
            parsed = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(parsed, dict):
            return None

        tool_name = parsed.get("tool", parsed.get("tool_name", ""))
        if not tool_name:
            return None

        if self._available_tools and tool_name not in self._available_tools:
            return None

        query = parsed.get("query", parsed.get("question", parsed.get("text", "")))
        parameters = parsed.get("parameters", parsed.get("params", {}))

        return ToolCall(
            tool_name=tool_name,
            action_input=match.group(),
            parameters={"query": query, "parameters": parameters},
            format_type="json",
        )

    def _try_parse_regex(self, text: str) -> Optional[ToolCall]:
        """尝试通过正则模式匹配工具调用。"""
        for pattern in _REGEX_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            tool_name = match.group(1).strip()

            # 忽略终止词
            if tool_name.lower() in _STOP_WORDS:
                continue

            # 验证工具可用性
            if self._available_tools and tool_name not in self._available_tools:
                continue

            # 提取 Action Input
            action_input = self._extract_regex_action_input(text, match)

            return ToolCall(
                tool_name=tool_name,
                action_input=action_input,
                parameters={"query": action_input, "parameters": {}},
                format_type="regex",
            )

        return None

    def _extract_regex_action_input(self, text: str, match: re.Match) -> str:
        """从正则匹配位置提取 Action Input 文本。"""
        after_tool = text[match.end():]

        input_match = re.search(
            r'(?:参数|输入|Action\s+Input)[：:]\s*(\{[^}]+\}|"[^"]*"|\'[^\']*\')',
            after_tool,
            re.DOTALL,
        )

        if input_match:
            return input_match.group(1)

        remaining = after_tool.strip()
        if remaining:
            return remaining.split("\n")[0][:500]

        return ""

    def _try_parse_text(self, text: str) -> Optional[ToolCall]:
        """纯文本模式：在可用工具中查找匹配。"""
        if not self._available_tools:
            return None

        for tool_name in self._available_tools:
            if tool_name in text:
                return ToolCall(
                    tool_name=tool_name,
                    action_input=text,
                    parameters={"query": text, "parameters": {}},
                    format_type="text",
                )

        return None