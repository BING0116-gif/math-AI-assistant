"""
ReActStrategy — ReAct 执行策略。

实现完整的 ReAct (Reasoning-Acting) 循环：
- Thought: LLM 分析问题，决定下一步行动
- Action: LLM 选择工具并生成调用参数
- Observation: 工具执行结果的反馈
- 循环直到得出最终答案或达到最大迭代次数

核心特点：
- 真流式输出：使用 astream_events() 从 LLM 级别逐 token 产出
- 工具调用时实时显示执行结果
- 完整的 ReAct 思维链记录

@deprecated 此模块已被 LangChainReActStrategy 取代。
           默认使用 LangChain 原生 ReAct Agent (function calling)。
           通过 MathAgent(use_langchain_agent=False) 可回退到此实现。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable

from agent_core.strategies.base import AgentStrategy
from agent_core.thought import ThoughtRecorder, ThoughtProcess
from tools.base_tool import BaseTool, ToolInput
from tools.hybrid_registry import HybridToolRegistry as ToolRegistry
from tools.tool_invoker import ToolInvoker

logger = logging.getLogger(__name__)

logger.debug(
    "ReActStrategy 已弃用（使用 LangChainReActStrategy 替代）。"
    "通过 MathAgent(use_langchain_agent=False) 可回退到此实现。"
)


# 工具调用的正则检测模式（预编译提升性能）
_TOOL_PATTERNS = [
    re.compile(r"Action:\s*(\w+)"),
    re.compile(r"使用?工具[：:]\s*(\w+)"),
]


class ReActStrategy(AgentStrategy):
    """
    ReAct 执行策略（真流式输出）。

    核心循环：Thought → Action → Observation → ... → Final Answer

    使用 astream_events() 实现 token 级别的流式输出，
    同时在流式过程中检测工具调用，实时展示解题过程。
    """

    def __init__(
        self,
        llm_chain: Runnable,
        registry: ToolRegistry,
        tools: List[BaseTool],
        max_iterations: int = 5,
        max_iteration_time_seconds: float = 60.0,
        thought_recorder: Optional[ThoughtRecorder] = None,
        llm_chain_sync: Optional[Runnable] = None,
    ):
        self._llm_chain = llm_chain
        self._llm_chain_sync = llm_chain_sync or llm_chain
        self._registry = registry
        self._tools = {tool.name: tool for tool in tools}
        self._invoker = ToolInvoker(registry)
        self._recorder = thought_recorder or ThoughtRecorder()
        self._max_iterations = max_iterations
        self._max_iteration_time = max_iteration_time_seconds
        self._tool_names = sorted(self._tools.keys())

    @property
    def tool_names(self) -> List[str]:
        return self._tool_names

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def thought_recorder(self) -> ThoughtRecorder:
        return self._recorder

    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> str:
        """异步执行 Agent（完整结果返回）。"""
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

        使用 astream_events() 从 LLM 级别逐 token 产出，
        同时在流式过程中检测工具调用，实时展示解题过程。
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

            collected_response = ""
            tool_call_detected = False
            stop_reason: Optional[str] = None  # "tool" | "final" | "iteration_end"

            try:
                # 使用 astream_events 捕获 LLM token 级别事件
                async for event in self._llm_chain.astream_events(invoke_data, version="v1"):
                    event_type = event.get("event", "")

                    # LLM 流式输出 token
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk is None:
                            continue
                        token = getattr(chunk, "content", None)
                        if not token:
                            continue

                        collected_response += token
                        yield token

                        # 边收边检测：是否触发工具调用
                        if not tool_call_detected:
                            tool_info = self._detect_tool_call(collected_response)
                            if tool_info:
                                tool_call_detected = True
                                stop_reason = "tool"
                                break

                    # LLM 生成结束
                    elif event_type == "on_chat_model_end":
                        # 如果没有检测到工具调用，检查是否直接输出最终答案
                        if not tool_call_detected:
                            stop_reason = "final"
                        break

                # 根据停止原因处理
                if tool_call_detected:
                    tool_info = self._detect_tool_call(collected_response)
                    if tool_info:
                        observation = await self._execute_tool(
                            tool_info, session_id, iteration, process
                        )
                        intermediate_steps.append({
                            "tool": tool_info["tool"],
                            "action": tool_info.get("input", ""),
                            "observation": observation,
                        })
                        yield observation
                        yield "\n\n"
                else:
                    final_answer = self._extract_final_answer(collected_response)
                    if final_answer:
                        self._recorder.finish(process, final_answer)
                        break

            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                yield f"\n\n**错误**: {e}"
                break

        yield "\n\n---\n\n**【最终答案】**\n\n"

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
                process, actual_tool, action_input,
                metadata={"iteration": iteration + 1}
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

    def _build_scratchpad(
        self, intermediate_steps: List[Dict[str, Any]]
    ) -> List[BaseMessage]:
        """构建 Agent 的中间步骤缓冲区。"""
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

    def _detect_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """
        检测文本中的工具调用。

        支持格式：
        - Action: tool_name
        - 工具: tool_name
        """
        # 快速检查：如果文本太短直接跳过
        if len(text) < 5:
            return None

        # 预编译模式匹配
        for pattern in _TOOL_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            tool_name = match.group(1).strip()

            # 忽略终止词
            if tool_name.lower() in (
                "final", "final answer", "none", "答案", "结束", ""
            ):
                continue

            # 必须是在工具注册表中存在的工具
            if tool_name not in self._tools:
                continue

            # 提取 Action Input
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

    def _extract_final_answer(self, llm_output: str) -> Optional[str]:
        """从 LLM 输出中提取最终答案。"""
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


# 向后兼容
StreamingReActStrategy = ReActStrategy

__all__ = [
    "ReActStrategy",
    "StreamingReActStrategy",
]
