"""
ToolPromptGenerator — 工具描述文本生成器。

从 ToolRegistry 中获取工具元数据，生成结构化、自然语言风格的工具描述，
供 LLM 理解可用工具集合并做出调用决策。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool


class ToolPromptGenerator:
    """
    工具描述文本生成器。

    将工具元数据转换为 LLM 可理解的标准化描述文本，
    支持多种格式：自然语言、JSON Schema、函数调用签名。

    Example:
        generator = ToolPromptGenerator()
        text = generator.generate_for_llm(registry.list_tools())
        json_schema = generator.generate_json_schema(registry.list_tools())
    """

    def __init__(self):
        self._include_examples: bool = True
        self._include_parameters: bool = True
        self._include_capabilities: bool = True

    def generate_for_llm(self, tools: List[Dict[str, Any]]) -> str:
        """
        生成供 LLM 理解的工具描述文本（自然语言风格）。

        Args:
            tools: 工具信息字典列表（通常来自 registry.list_tools()）。

        Returns:
            格式化的工具描述文本块。
        """
        if not tools:
            return "当前无可用工具。"

        descriptions = []
        for tool in tools:
            desc = self._format_single_tool(tool)
            descriptions.append(desc)

        header = "## 可用工具列表\n"
        return header + "\n\n".join(descriptions)

    def _format_single_tool(self, tool: Dict[str, Any]) -> str:
        """格式化单个工具的描述。"""
        name = tool.get("name", "unknown")
        desc = tool.get("description", "无描述")
        version = tool.get("version", "1.0.0")
        capabilities = tool.get("capabilities", [])

        lines = [
            f"### 工具名: {name}",
            f"**功能描述**: {desc}",
        ]

        if self._include_capabilities and capabilities:
            caps_str = "、".join(str(c) for c in capabilities)
            lines.append(f"**能力标签**: {caps_str}")

        lines.append(f"**版本**: {version}")

        if self._include_parameters:
            input_schema = tool.get("input_schema", {})
            params = input_schema.get("properties", {})
            if params:
                lines.append("**输入参数**:")
                for param_name, param_info in params.items():
                    param_desc = param_info.get("description", "无描述")
                    param_type = param_info.get("type", "any")
                    lines.append(f"  - `{param_name}` ({param_type}): {param_desc}")

        return "\n".join(lines)

    def generate_json_schema(self, tools: List[Dict[str, Any]]) -> str:
        """
        生成 JSON Schema 格式的工具描述（用于函数调用场景）。

        Args:
            tools: 工具信息字典列表。

        Returns:
            JSON Schema 格式的工具定义。
        """
        if not tools:
            return json.dumps({"tools": []}, ensure_ascii=False, indent=2)

        schema_tools = []
        for tool in tools:
            schema_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                    "parameters": self._build_parameters_schema(tool),
                },
            }
            schema_tools.append(schema_tool)

        return json.dumps({"tools": schema_tools}, ensure_ascii=False, indent=2)

    def _build_parameters_schema(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """构建工具参数 Schema。"""
        input_schema = tool.get("input_schema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        if not properties:
            return {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户问题或工具输入文本",
                    },
                },
                "required": ["query"],
            }

        return {
            "type": "object",
            "properties": properties,
            "required": required if required else ["query"],
        }

    def generate_structured_list(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成结构化的工具列表（字典格式）。

        Args:
            tools: 工具信息字典列表。

        Returns:
            结构化的工具信息列表。
        """
        result = []
        for tool in tools:
            result.append({
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", ""),
                "version": tool.get("version", "1.0.0"),
                "capabilities": tool.get("capabilities", []),
                "input_schema": tool.get("input_schema", {}),
            })
        return result

    def set_include_examples(self, include: bool) -> "ToolPromptGenerator":
        """设置是否包含使用示例。"""
        self._include_examples = include
        return self

    def set_include_parameters(self, include: bool) -> "ToolPromptGenerator":
        """设置是否包含参数信息。"""
        self._include_parameters = include
        return self

    def set_include_capabilities(self, include: bool) -> "ToolPromptGenerator":
        """设置是否包含能力标签。"""
        self._include_capabilities = include
        return self
