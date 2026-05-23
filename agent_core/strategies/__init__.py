"""
agent_core/strategies 包 — Agent 执行策略层。

提供可插拔的 Agent 执行策略：
- ReActStrategy: 完整的 ReAct 思维链循环，真流式输出（打字机效果）
- LangChainReActStrategy: 基于LangChain原生的ReAct策略（推荐）
- PlannedStrategy: 按计划执行策略，支持 DAG 调度和并行执行
"""

from agent_core.strategies.base import AgentStrategy
from agent_core.strategies.react import ReActStrategy

# 向后兼容：StreamingReActStrategy 是 ReActStrategy 的别名
from agent_core.strategies.react import StreamingReActStrategy
from agent_core.strategies.planned import PlannedStrategy
from agent_core.strategies.langchain_react import LangChainReActStrategy

__all__ = [
    "AgentStrategy",
    "ReActStrategy",
    "StreamingReActStrategy",  # 向后兼容别名
    "PlannedStrategy",
    "LangChainReActStrategy",
]
