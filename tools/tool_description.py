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

    def generate_markdown_table(self, tools: List[BaseTool]) -> str:
        """
        生成 Markdown 表格格式的工具列表。

        Args:
            tools: BaseTool 实例列表。

        Returns:
            Markdown 表格字符串。
        """
        if not tools:
            return "| 工具名 | 描述 | 能力 | 版本 |\n|---|---|---|---|\n*(无工具)* |"

        lines = ["| 工具名 | 描述 | 能力 | 版本 |", "|---|---|---|---|"]
        for tool in tools:
            caps = ", ".join(c.value for c in tool.capabilities) if tool.capabilities else "-"
            name = tool.name
            desc = tool.description[:50] + ("..." if len(tool.description) > 50 else "")
            lines.append(f"| {name} | {desc} | {caps} | {tool.version} |")

        return "\n".join(lines)

    def generate_json_output(self, tools: List[BaseTool]) -> str:
        """
        生成 JSON 格式的工具列表。

        Args:
            tools: BaseTool 实例列表。

        Returns:
            JSON 字符串。
        """
        schemas = self.generate_all_schemas(tools)
        return json.dumps(schemas, ensure_ascii=False, indent=2)

    def set_markdown_mode(self, enabled: bool) -> "ToolDescriptionGenerator":
        """设置 Markdown 模式。"""
        self._markdown_mode = enabled
        return self

    def set_include_examples(self, enabled: bool) -> "ToolDescriptionGenerator":
        """设置是否包含示例。"""
        self._include_examples = enabled
        return self

    def set_include_capabilities(self, enabled: bool) -> "ToolDescriptionGenerator":
        """设置是否包含能力标签。"""
        self._include_capabilities = enabled
        return self

    def set_include_parameters(self, enabled: bool) -> "ToolDescriptionGenerator":
        """设置是否包含参数信息。"""
        self._include_parameters = enabled
        return self
