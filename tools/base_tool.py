"""
BaseTool 抽象基类与数据模型。

定义所有工具必须实现的标准化接口，是 ToolRegistry 插件系统的核心契约。
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCapability(str, Enum):
    """工具能力枚举 — 所有可用能力的标准化标签集。"""
    SYMBOLIC_COMPUTATION = "symbolic_computation"
    NUMERICAL_COMPUTATION = "numerical_computation"
    IMAGE_RECOGNITION = "image_recognition"
    FORMULA_RECOGNITION = "formula_recognition"
    PLOTTING = "plotting"
    PRACTICE_GENERATION = "practice_generation"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    VERIFICATION = "verification"
    ERROR_BOOK_MANAGEMENT = "error_book_management"


class ToolInput(BaseModel):
    """工具输入标准模型 — 所有工具的入参结构。"""
    query: str = Field(..., description="用户问题或工具输入文本")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="工具执行参数（如图像数据、计算参数）"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="上下文信息（用户历史、会话状态等）"
    )


class ToolOutput(BaseModel):
    """工具输出标准模型 — 所有工具的出参结构。"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(None, description="执行结果数据")
    data: Dict[str, Any] = Field(default_factory=dict, description="结构化数据（供前端/Agent使用）")
    error: Optional[str] = Field(None, description="错误信息")
    tool_name: str = Field("", description="执行工具名称")
    execution_time_ms: float = Field(0.0, description="执行耗时（毫秒）")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="附加元数据"
    )


class BaseTool(ABC):
    """
    工具抽象基类 — 插件系统的核心接口。

    所有工具必须继承此类并实现 execute() 方法。
    工具通过 ToolRegistry.register() 注册后即可被 Agent 系统发现和调用。

    Attributes:
        name: 工具唯一标识符（全局唯一，用于注册和检索）
        description: 工具功能的自然语言描述（供 LLM 理解）
        version: 工具版本号（语义化版本）
        capabilities: 工具能力标签列表（用于能力搜索和匹配）

    Example:
        class MathSolverTool(BaseTool):
            name = "math_solver"
            description = "数学符号计算与求解"
            capabilities = [ToolCapability.SYMBOLIC_COMPUTATION, ToolCapability.VERIFICATION]

            async def execute(self, input_data: ToolInput) -> ToolOutput:
                result = sympy.solve(input_data.query)
                return ToolOutput(success=True, result=str(result), tool_name=self.name)
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[ToolCapability] = []

    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """
        执行工具逻辑。

        Args:
            input_data: 标准化的工具输入。

        Returns:
            ToolOutput: 标准化的工具输出。

        Raises:
            ToolExecutionError: 工具执行失败时抛出。
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """
        返回工具完整信息（用于注册发现、文档生成、LLM 工具描述）。

        Returns:
            包含 name、description、version、capabilities、input_schema 的字典。
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": ToolInput.model_json_schema(),
        }

    def get_description_for_llm(self) -> str:
        """
        生成供 LLM 理解的工具描述文本。

        Returns:
            格式化的工具描述字符串。
        """
        caps = ", ".join(cap.value for cap in self.capabilities)
        return f"工具名: {self.name}\n描述: {self.description}\n能力: {caps}\n版本: {self.version}"

    def validate_input(self, input_data: ToolInput) -> Optional[str]:
        """
        验证输入数据的合法性（子类可覆写以添加自定义校验）。

        Args:
            input_data: 待验证的输入。

        Returns:
            错误信息字符串，验证通过返回 None。
        """
        if not input_data.query.strip():
            return "输入查询不能为空"
        return None
