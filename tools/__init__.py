"""
工具层初始化 — 注册所有工具到 HybridToolRegistry。
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.hybrid_registry import HybridToolRegistry, ToolNotFoundError, ToolExecutionError
from tools.vision_tool import VisionTool, VisionToolAdapter
from tools.recommend_tool import RecommendTool
from tools.skill_profile_tool import SkillProfileTool
from tools.explain_tool import ExplainTool
from tools.search_tool import SearchTool
from tools.error_book_tool import ErrorBookTool
from tools.ask_student_tool import AskStudentTool
from tools.math_verify_tool import MathVerifyTool
from tools.math_visualize_tool import MathVisualizeTool

_registry: HybridToolRegistry = None


def get_registry() -> HybridToolRegistry:
    global _registry
    if _registry is None:
        _registry = HybridToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def init_registry(registry: HybridToolRegistry = None) -> HybridToolRegistry:
    """初始化或替换全局注册表单例（用于测试或自定义配置）。"""
    global _registry
    _registry = registry or HybridToolRegistry()
    return _registry


def _register_builtin_tools(registry: HybridToolRegistry, api_key: str = None) -> None:
    """注册所有内置工具。"""
    if api_key is None:
        try:
            from app.config.settings import settings
            api_key = settings.DASHSCOPE_API_KEY
        except Exception:
            pass

    if api_key:
        vision = VisionTool(api_key=api_key)
        registry.register(VisionToolAdapter(vision))

    registry.register(RecommendTool())
    registry.register(SkillProfileTool())
    registry.register(ExplainTool())
    registry.register(SearchTool())
    registry.register(ErrorBookTool())
    registry.register(AskStudentTool())
    registry.register(MathVerifyTool())
    registry.register(MathVisualizeTool())


ToolRegistry = HybridToolRegistry


__all__ = [
    "BaseTool",
    "ToolInput",
    "ToolOutput",
    "ToolCapability",
    "HybridToolRegistry",
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolExecutionError",
    "MathVerifyTool",
    "MathVisualizeTool",
    "get_registry",
    "init_registry",
]
