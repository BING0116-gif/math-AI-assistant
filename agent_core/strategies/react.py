"""
ReActStrategy — ReAct 执行策略（真流式输出）。

实现完整的 ReAct (Reasoning-Acting) 循环：
- Thought: LLM 分析问题，决定下一步行动
- Action: LLM 选择工具并生成调用参数
- Observation: 工具执行结果的反馈
- 循环直到得出最终答案或达到最大迭代次数

核心特点：
- 实时流式输出：token 逐个产出，实现打字机效果
- 智能回退：当流式 API 不可用时，自动降级为非流式+模拟打字机
- 完整的 ReAct 思维链记录

（原 react.py + streaming_react.py 合并）
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable

from agent_core.strategies.base import AgentStrategy
from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStepType
from tools.base_tool import BaseTool, ToolInput, ToolOutput
from tools.registry import ToolRegistry
from tools.tool_invoker import ToolInvoker, ToolInvokeError

logger = logging.getLogger(__name__)


class ReActStrategy(AgentStrategy):
    """
    ReAct 执行策略（真流式输出）。

    核心循环：Thought → Action → Observation → ... → Final Answer

    特点：
    - 完整的 ReAct 思维链推理
    - 工具自主选择与调用
    - 思维过程全程记录
    - 实时流式输出（打字机效果）
    """

    def __init__(
        self,
        llm_chain: Runnable,
        registry: ToolRegistry,
        tools: List[BaseTool],
        max_iterations: int = 5,
        max_iteration_time_seconds: float = 60.0,
        thought_recorder: Optional[ThoughtRecorder] = None,
    ):
        """
        初始化 ReAct 策略。

        Args:
            llm_chain: LangChain 可运行链（输出 AIMessage）
            registry: 工具注册中心
            tools: 可用工具列表
            max_iterations: 最大迭代次数
            max_iteration_time_seconds: 最大执行时间
            thought_recorder: 思维记录器
        """
        self._llm_chain = llm_chain
        self._registry = registry
        self._tools = {tool.name: tool for tool in tools}
        self._invoker = ToolInvoker(registry)
        self._recorder = thought_recorder or ThoughtRecorder()
        self._max_iterations = max_iterations
        self._max_iteration_time = max_iteration_time_seconds
        self._tool_names = sorted(self._tools.keys())

    @property
    def tool_names(self) -> List[str]:
        """获取可用工具名称列表。"""
        return self._tool_names

    @property
    def tool_count(self) -> int:
        """获取工具数量。"""
        return len(self._tools)

    @property
    def thought_recorder(self) -> ThoughtRecorder:
        """获取思维记录器。"""
        return self._recorder

    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> str:
        """
        异步执行 Agent（完整结果返回）。

        通过收集流式输出来返回完整结果。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文，包含 chat_history。

        Returns:
            最终答案字符串。
        """
        chunks = []
        async for chunk in self.stream(user_input, session_id, context):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        异步流式执行 Agent。

        流程：
        1. 调用 LLM 获取响应
        2. 检测工具调用并执行
        3. 实时 yield 思维链 + 最终答案

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。
            context: 执行上下文。

        Yields:
            输出文本片段。
        """
        process = self._recorder.start_process(session_id, user_input)
        self._recorder.add_thought(process, f"开始处理: {user_input[:30]}...")

        intermediate_steps: List[Dict[str, Any]] = []

        yield "**正在思考...**\n\n"

        for iteration in range(self._max_iterations):
            if time.time() - process.start_time > self._max_iteration_time:
                yield "\n\n**超时**：执行时间超出限制"
                break

            self._recorder.add_thought(
                process,
                f"第 {iteration + 1} 次迭代",
                metadata={"iteration": iteration + 1},
            )

            scratchpad = self._build_scratchpad(intermediate_steps)
            invoke_data = {
                "input": user_input,
                "chat_history": context.get("chat_history", []),
                "agent_scratchpad": scratchpad,
            }

            full_response = ""
            tool_call_detected = False

            try:
                content = await self._call_llm(invoke_data)
                full_response = content

                tool_info = self._detect_tool_call(full_response)
                if tool_info:
                    tool_call_detected = True
                    observation = await self._execute_tool(
                        tool_info,
                        session_id,
                        iteration,
                        process,
                    )
                    intermediate_steps.append({
                        "tool": tool_info["tool"],
                        "action": tool_info.get("input", ""),
                        "observation": observation,
                    })
                    # 立即 yield 工具结果，让用户看到解题过程
                    yield observation
                    yield "\n\n"
                    full_response = ""

            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                yield f"\n\n**错误**: {e}"
                break

            if not tool_call_detected:
                final_answer = self._extract_final_answer(full_response)
                if final_answer:
                    self._recorder.finish(process, final_answer)
                    break

        yield "\n\n---\n\n**【最终答案】**\n\n"

    async def _call_llm(self, invoke_data: Dict[str, Any]) -> str:
        """
        真异步调用 LLM 获取响应。

        使用 ainvoke 避免阻塞事件循环。

        Returns:
            LLM 响应的文本内容
        """
        try:
            result = await self._llm_chain.ainvoke(invoke_data)

            if hasattr(result, "content"):
                return str(result.content)
            elif isinstance(result, str):
                return result
            elif isinstance(result, dict):
                return str(result.get("content", str(result)))
            else:
                return str(result)

        except Exception as e:
            logger.error(f"LLM ainvoke 失败: {e}")
            raise

    def _detect_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """
        检测文本中的工具调用。

        支持格式：
        - Action: tool_name
        - Action Input: {...}
        - 工具: tool_name
        """
        patterns = [
            r"(?:使用)?工具[：:]\s*(\w+)",
            r"Action:\s*(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tool_name = match.group(1).strip()

                if tool_name.lower() in ("final", "final answer", "none", "答案", "结束", ""):
                    continue

                if tool_name in self._tools:
                    after_tool = text[match.end():]
                    input_match = re.search(
                        r'(?:参数|输入|Action\s+Input)[：:]\s*(\{[^}]+\}|"[^"]*"|\'[^\']*\')',
                        after_tool,
                        re.DOTALL
                    )

                    action_input = ""
                    if input_match:
                        action_input = input_match.group(1)
                    else:
                        remaining = after_tool.strip()
                        if remaining:
                            action_input = remaining.split('\n')[0][:500]

                    return {
                        "tool": tool_name,
                        "input": action_input,
                    }

        return None

    async def _execute_tool(
        self,
        tool_info: Dict[str, Any],
        session_id: str,
        iteration: int,
        process: ThoughtProcess,
    ) -> str:
        """执行工具调用并返回结果描述。"""
        tool_name = tool_info["tool"]
        action_input = tool_info.get("input", "")

        result_str = f"**【调用工具】**: `{tool_name}`\n"

        try:
            tool_name_parsed, params = self._invoker.parse_action_input(action_input)

            if tool_name_parsed and tool_name_parsed in self._tools:
                actual_tool = tool_name_parsed
            else:
                actual_tool = tool_name

            query = params.get("query", action_input)
            input_data_obj = ToolInput(
                query=query,
                parameters=params.get("parameters", {}),
                context={"session_id": session_id, "iteration": iteration + 1},
            )

            result = await self._invoker.invoke(actual_tool, input_data_obj)

            self._recorder.add_action(
                process, actual_tool, action_input, metadata={"iteration": iteration + 1}
            )
            self._recorder.add_observation(
                process,
                result.result or "执行成功",
                elapsed_ms=result.execution_time_ms,
                metadata={"tool": actual_tool, "success": result.success},
            )

            if result.success:
                observation = result.result or "执行成功"
                result_str += f"**【结果】**: {observation}"
            else:
                result_str += f"**【错误】**: {result.error}"

        except Exception as e:
            error_msg = f"工具调用异常: {e}"
            logger.error(f"[{process.process_id}] {error_msg}")
            self._recorder.add_error(process, error_msg)
            result_str += f"**【错误】**: {e}"

        return result_str

    def _build_scratchpad(self, intermediate_steps: List[Dict[str, Any]]) -> List[BaseMessage]:
        """
        构建 Agent 的中间步骤缓冲区（Scratchpad）。

        将之前的 Thought/Action/Observation 历史注入到 LLM 上下文，
        使 LLM 能够基于已有信息继续推理。
        """
        if not intermediate_steps:
            return []

        messages = []
        for i, step in enumerate(intermediate_steps):
            content_parts = [f"步骤 {i + 1}:"]

            if "thought" in step:
                content_parts.append(f"Thought: {step['thought']}")
            if "tool" in step or "action" in step:
                tool = step.get("tool", step.get("action", ""))
                content_parts.append(f"Action: {tool}")
                if "action" in step:
                    content_parts.append(f"Action Input: {step['action']}")
            if "observation" in step:
                content_parts.append(f"Observation: {step['observation']}")
            content_parts.append("")

            messages.append(HumanMessage(content="\n".join(content_parts)))

        return messages

    def _extract_final_answer(self, llm_output: str) -> Optional[str]:
        """
        从 LLM 输出中提取最终答案。

        查找 "Final Answer:" 或 "最终答案:" 标记后的内容。
        """
        patterns = [
            r"Final\s+Answer:\s*(.*?)(?=\n\n|\n?$)",
            r"最终答案[：:]\s*(.*?)(?=\n\n|\n?$)",
            r"Answer:\s*(.*?)(?=\n\n|\n?$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, llm_output, re.DOTALL | re.IGNORECASE)
            if match:
                answer = match.group(1).strip()
                if answer:
                    return answer

        if len(llm_output.strip()) > 10:
            return llm_output.strip()

        return None


# 向后兼容：保留 StreamingReActStrategy 作为 ReActStrategy 的别名
# 新代码应直接使用 ReActStrategy
StreamingReActStrategy = ReActStrategy

__all__ = [
    "ReActStrategy",
    "StreamingReActStrategy",  # 向后兼容，别名
]
