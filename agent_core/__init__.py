"""
agent_core 包 — Agent 核心层。

提供统一的 MathAgent 和相关组件。
"""

from agent_core.agent import MathAgent, create_math_agent
from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStepType

__all__ = [
    "MathAgent",
    "create_math_agent",
    "ThoughtRecorder",
    "ThoughtProcess",
    "ThoughtStepType",
]
