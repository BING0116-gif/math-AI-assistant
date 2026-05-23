"""
tools 包 — 工具基础设施层。

导出 BaseTool、HybridToolRegistry 等核心组件，提供全局 Registry 单例。

升级说明 (v2.0)：
- 默认全局注册表已升级为 HybridToolRegistry（支持LangChain双模式）
- 原有 ToolRegistry 作为兼容性别名保留（指向 HybridToolRegistry）
- 所有原有 API 完全向后兼容
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.hybrid_registry import (
    HybridToolRegistry,
    ToolNotFoundError,
    ToolExecutionError,
)

# 兼容性别名：保留原有导入路径
ToolRegistry = HybridToolRegistry

logger = logging.getLogger(__name__)

_registry: Optional[HybridToolRegistry] = None


def get_registry() -> HybridToolRegistry:
    """
    获取全局 HybridToolRegistry 单例。

    首次调用时自动初始化并注册所有内置工具。
    返回的注册表支持双模式：
    - 自定义模式：保留能力标签、版本管理、统计等功能
    - LangChain模式：提供 get_langchain_tools() 供 Agent 使用

    Returns:
        HybridToolRegistry 全局实例。
    """
    global _registry
    if _registry is None:
        _registry = HybridToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def init_registry(registry: Optional[HybridToolRegistry] = None) -> HybridToolRegistry:
    """
    初始化或替换全局注册表单例（用于测试或自定义配置）。

    Args:
        registry: 可选的 HybridToolRegistry 实例。
                  为 None 时创建新实例。

    Returns:
        初始化后的 HybridToolRegistry 实例。
    """
    global _registry
    _registry = registry or HybridToolRegistry()
    return _registry


def _register_builtin_tools(
    registry: HybridToolRegistry, api_key: Optional[str] = None
) -> None:
    """
    注册所有内置工具。

    Args:
        registry: HybridToolRegistry 实例。
        api_key: 可选的 API 密钥（用于 VisionTool）。
                 如果为 None，将尝试从 settings 获取。
    """
    if api_key is None:
        try:
            from app.config.settings import settings
            api_key = settings.DASHSCOPE_API_KEY
        except Exception:
            logger.info("无法获取 API Key，跳过内置工具注册")
            return

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
    "HybridToolRegistry",
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolExecutionError",
    "get_registry",
    "init_registry",
]
