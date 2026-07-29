"""
PlannedStrategy — 复杂任务的规划执行策略。

当前为桩模块，提供最小接口供测试导入。
实际实现将在后续迭代中完成。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, Optional

from agent_core.strategies.base import AgentStrategy

logger = logging.getLogger(__name__)


class PlannedStrategy(AgentStrategy):
    """
    复杂任务的规划执行策略。

    将复杂问题分解为有向无环图（DAG）任务，串行或并行执行子任务。
    """

    def __init__(
        self,
        llm_chain: Any,
        registry: Any,
        task_planner: Any = None,
        thought_recorder: Any = None,
    ):
        self._llm_chain = llm_chain
        self._registry = registry
        self._task_planner = task_planner
        self._thought_recorder = thought_recorder

    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
        plan: Optional[Any] = None,
    ) -> str:
        """
        执行规划任务。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文。
            plan: 执行计划（可选）。

        Returns:
            执行结果字符串。
        """
        result = await self._llm_chain.ainvoke(user_input)
        if hasattr(result, "content"):
            return result.content
        return str(result)

    async def stream(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
        plan: Optional[Any] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式执行规划任务。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文。
            plan: 执行计划（可选）。

        Yields:
            输出文本片段。
        """
        if plan is None:
            yield "错误: 未提供执行计划，无法执行流式输出"
            return

        result = await self._llm_chain.ainvoke(user_input)
        if hasattr(result, "content"):
            text = result.content
        else:
            text = result
        yield str(text)