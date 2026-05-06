"""
tools 包 — 工具基础设施层。

导出 BaseTool、ToolRegistry 等核心组件，提供全局 Registry 单例。
"""

from __future__ import annotations

import logging

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.registry import ToolRegistry, ToolNotFoundError, ToolExecutionError

logger = logging.getLogger(__name__)

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """
    获取全局 ToolRegistry 单例。

    首次调用时自动初始化并注册所有内置工具。

    Returns:
        ToolRegistry 全局实例。
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def _register_builtin_tools(registry: ToolRegistry, api_key: str | None = None) -> None:
    """
    注册所有内置工具。

    Args:
        registry: ToolRegistry 实例。
        api_key: 可选的 API 密钥（用于 VisionTool）。如果为 None，将尝试从 settings 获取。
    """
    if api_key is None:
        from app.config.settings import settings

        api_key = settings.DASHSCOPE_API_KEY

    if api_key:
        from tools.vision_tool import VisionTool, VisionToolAdapter

        vision = VisionTool(api_key=api_key)
        registry.register(VisionToolAdapter(vision))

    logger.info(f"内置工具注册完成，共 {registry.tool_count} 个工具")


__all__ = [
    "BaseTool",
    "ToolInput",
    "ToolOutput",
    "ToolCapability",
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolExecutionError",
    "get_registry",
]
