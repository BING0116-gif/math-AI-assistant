"""
agent_core 包 — Agent 核心层。

提供统一的 MathAgent 和相关组件。
"""

from agent_core.agent import (
    MathAgent,
    create_math_agent,
    MathAgentConfig,
    LLMConfig,
    StrategyConfig,
    DynamicParamsConfig,
)
from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStepType
from agent_core.strategies.langchain_react import LangChainReActStrategy
from agent_core.callbacks import ThoughtRecordingCallbackHandler
from agent_core.langchain_adapter import LangChainToolConverter, get_tool_converter, convert_tools_to_langchain


__all__ = [
    "MathAgent",
    "create_math_agent",
    "MathAgentConfig",
    "LLMConfig",
    "StrategyConfig",
    "DynamicParamsConfig",
    "ThoughtRecorder",
    "ThoughtProcess",
    "ThoughtStepType",
    "LangChainReActStrategy",
    "ThoughtRecordingCallbackHandler",
    "LangChainToolConverter",
    "get_tool_converter",
    "convert_tools_to_langchain",
]
