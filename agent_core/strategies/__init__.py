"""
agent_core/strategies 包 — Agent 执行策略层。

提供可插拔的 Agent 执行策略：
- ReActStrategy: 完整的 ReAct 思维链循环，真流式输出（打字机效果）
"""

from agent_core.strategies.base import AgentStrategy
from agent_core.strategies.react import ReActStrategy

# 向后兼容：StreamingReActStrategy 是 ReActStrategy 的别名
from agent_core.strategies.react import StreamingReActStrategy

__all__ = [
    "AgentStrategy",
    "ReActStrategy",
    "StreamingReActStrategy",  # 向后兼容别名
]
