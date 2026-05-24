"""
agent_core 包 — Agent 核心层。

提供统一的 MathAgent 和相关组件。
"""

from agent_core.agent import MathAgent, create_math_agent
from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStepType
from agent_core.task_planner import (
    TaskPlanner,
    TaskDAG,
    Task,
    TaskStatus,
    TaskPriority,
    ExecutionPlan,
    PlanningContext,
    PlannerConfig,
    PlanningError,
    CircularDependencyError,
)
from agent_core.strategies.planned import PlannedStrategy
from agent_core.strategies.langchain_react import LangChainReActStrategy
from agent_core.callbacks import ThoughtRecordingCallbackHandler
from agent_core.langchain_adapter import LangChainToolConverter, get_tool_converter, convert_tools_to_langchain

from agent_core.classifier import (
    LLMComplexityClassifier,
    ClassificationResult,
    ClassifierConfig,
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)

__all__ = [
    "MathAgent",
    "create_math_agent",
    "ThoughtRecorder",
    "ThoughtProcess",
    "ThoughtStepType",
    "TaskPlanner",
    "TaskDAG",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "ExecutionPlan",
    "PlanningContext",
    "PlannerConfig",
    "PlanningError",
    "CircularDependencyError",
    "PlannedStrategy",
    "LangChainReActStrategy",
    "ThoughtRecordingCallbackHandler",
    "LangChainToolConverter",
    "get_tool_converter",
    "convert_tools_to_langchain",
    "LLMComplexityClassifier",
    "ClassificationResult",
    "ClassifierConfig",
    "ComplexityLevel",
    "ComplexityCategory",
    "level_to_strategy",
    "is_simple",
    "is_complex",
]
