"""
AgentStrategy — Agent 执行策略抽象基类。

定义策略接口，所有具体执行策略（ReAct、Simple 等）必须实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional


class AgentStrategy(ABC):
    """
    Agent 执行策略抽象基类。

    策略封装了 Agent 的核心执行逻辑（如何调用 LLM、如何处理工具、
    如何管理思维链），使 MathAgent 能够通过注入不同策略来切换行为模式。

    所有策略共享相同的接口定义，上层调用方（MathAgent）无需关心具体实现。
    """

    @abstractmethod
    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> str:
        """
        同步执行，返回完整答案。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文（包含 chat_history 等）。

        Returns:
            最终答案字符串。
        """
        pass

    @abstractmethod
    async def stream(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        异步流式执行，yield 文本片段。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文。

        Yields:
            输出文本片段。
        """
        yield ""
