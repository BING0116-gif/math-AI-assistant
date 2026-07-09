"""
agent_core/strategies 包 — Agent 执行策略层。

提供可插拔的 Agent 执行策略：
- LangChainReActStrategy: 基于LangChain原生的ReAct策略（推荐）
"""

from agent_core.strategies.base import AgentStrategy
from agent_core.strategies.langchain_react import LangChainReActStrategy

__all__ = [
    "AgentStrategy",
    "LangChainReActStrategy",
]