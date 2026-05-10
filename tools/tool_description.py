"""
ToolDescriptionGenerator — 增强版工具描述生成器。

从 BaseTool 实例生成结构化、LLM友好的工具描述，
支持 JSON Schema、Markdown、自然语言等多种格式。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolCapability


class ToolDescriptionGenerator:
    """
    增强版工具描述生成器。

    将 BaseTool 实例转换为多种格式的描述文本，
    支持：自然语言、JSON Schema、函数调用签名。

    Example:
        generator = ToolDescriptionGenerator()
        text = generator.generate_text(tool)
        schema = generator.generate_json_schema(tool)
    """

    def __init__(self):
        self._include_examples: bool = True
        self._include_capabilities: bool = True
        self._include_parameters: bool = True
        self._markdown_mode: bool = True

    def generate_for_registry(self, tools: List[BaseTool]) -> str:
        """
        为 ToolRegistry 生成所有工具的描述文本。

        Args:
            tools: BaseTool 实例列表。

        Returns:
            格式化的工具描述文本。
        """
        if not tools:
            return "当前无可用工具。"

        descriptions = []
        for tool in tools:
            desc = self.generate_text(tool)
            descriptions.append(desc)

        header = "当前可用工具列表：\n" + "=" * 40
        return header + "\n\n" + "\n\n".join(descriptions)

    def generate_text(self, tool: BaseTool) -> str:
        """
        生成单个工具的自然语言描述文本。

        Args:
            tool: BaseTool 实例。

        Returns:
            格式化的工具描述。
        """
        lines = [
            f"工具名: {tool.name}",
            f"描述: {tool.description}",
        ]

        if self._include_capabilities and tool.capabilities:
            caps = ", ".join(c.value for c in tool.capabilities)
            lines.append(f"能力: {caps}")

        lines.append(f"版本: {tool.version}")

        if self._include_parameters:
            schema = tool.get_info()
            input_schema = schema.get("input_schema", {})
            properties = input_schema.get("properties", {})
            if properties:
                lines.append("输入参数:")
                for param_name, param_info in properties.items():
                    desc = param_info.get("description", "无描述")
                    ptype = param_info.get("type", "string")
                    required = input_schema.get("required", [])
                    req_mark = "(必填)" if param_name in required else "(可选)"
                    lines.append(f"  - {param_name} ({ptype}) {req_mark}: {desc}")

        return "\n".join(lines)

    def generate_json_schema(self, tool: BaseTool) -> Dict[str, Any]:
        """
        生成单个工具的 JSON Schema 格式描述。

        Args:
            tool: BaseTool 实例。

        Returns:
            JSON Schema 字典。
        """
        info = tool.get_info()
        properties = info.get("input_schema", {}).get("properties", {})
        required = info.get("input_schema", {}).get("required", [])

        schema_properties: Dict[str, Any] = {}
        for param_name, param_info in properties.items():
            schema_properties[param_name] = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
            }

        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": schema_properties,
                "required": required if required else ["query"],
            },
        }

    def generate_function_call(self, tool: BaseTool) -> Dict[str, Any]:
        """
        生成函数调用格式的工具定义（OpenAI function calling 风格）。

        Args:
            tool: BaseTool 实例。

        Returns:
            函数定义字典。
        """
        schema = self.generate_json_schema(tool)
        return {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
        }

    def generate_all_schemas(self, tools: List[BaseTool]) -> List[Dict[str, Any]]:
        """
        为所有工具生成函数调用格式定义。

        Args:
            tools: BaseTool 实例列表。

        Returns:
            函数定义列表。
        """
        return [self.generate_function_call(tool) for tool in tools]

    def generate_structured_list(self, tools: List[BaseTool]) -> List[Dict[str, Any]]:
        """
        生成结构化的工具列表（字典格式）。

        Args:
            tools: BaseTool 实例列表（或工具信息字典列表）。

        Returns:
            结构化的工具信息列表。
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append({
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                    "version": tool.get("version", "1.0.0"),
                    "capabilities": tool.get("capabilities", []),
                    "input_schema": tool.get("input_schema", {}),
                })
            else:
                info = tool.get_info()
                result.append({
                    "name": info.get("name", "unknown"),
                    "description": info.get("description", ""),
                    "version": info.get("version", "1.0.0"),
                    "capabilities": info.get("capabilities", []),
                    "input_schema": info.get("input_schema", {}),
                })
        return result
