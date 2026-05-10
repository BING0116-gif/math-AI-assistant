"""
MathAgent — 统一的数学解题 Agent。

通过策略模式支持多种执行模式，默认使用 ReAct 完整思维链推理。

架构：
- MathAgent: 统一入口，管理 LLM、Session、工具注册、图片处理
- AgentStrategy: 执行策略抽象基类
- ReActStrategy: 完整的 ReAct 思维链循环，真流式输出（打字机效果）
- PlannedStrategy: 按 TaskPlanner 生成的计划调度执行（复杂问题）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agent_core.strategies import AgentStrategy, ReActStrategy, PlannedStrategy
from agent_core.thought import ThoughtRecorder
from agent_core.task_planner import (
    TaskPlanner,
    PlannerConfig,
    PlanningContext,
)
from prompts.system_prompt import SystemPromptManager
from prompts.react_prompt import ReActPromptTemplate
from tools import get_registry, ToolRegistry, BaseTool, ToolInput
from tools.tool_description import ToolDescriptionGenerator

logger = logging.getLogger(__name__)


class MathAgent:
    """
    统一的数学解题 Agent。

    通过策略模式注入执行逻辑，所有模式共享：
    - 统一的 LLM 初始化
    - 统一的会话历史管理（InMemoryChatMessageHistory）
    - 统一的图片输入处理（VisionTool）
    - 统一的流式输出基础设施

    默认使用 ReAct 执行策略，具备完整工具调用和思维链记录能力。

    Example:
        agent = MathAgent(api_key="your-key")
        result = await agent.process("求∫x²dx", session_id="user_1")
        async for chunk in agent.stream("求极限"):
            print(chunk, end="")
    """

    def __init__(
        self,
        api_key: str,
        registry: Optional[ToolRegistry] = None,
        model: str = "qwen-max",
        temperature: float = 0,
        max_iterations: int = 5,
        stream: bool = True,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        enable_planner: bool = True,
    ):
        assert api_key, "API 密钥必须提供"

        self._api_key = api_key
        self._registry = registry or get_registry()
        self._model = model
        self._temperature = temperature
        self._max_iterations = max_iterations
        self._stream_enabled = stream
        self._base_url = base_url
        self._default_session_id = "default"
        self._session_histories: Dict[str, InMemoryChatMessageHistory] = {}
        self._strategy: Optional[AgentStrategy] = None
        self._enable_planner = enable_planner
        self._planned_strategy: Optional[PlannedStrategy] = None

        # 统一 LLM 实例
        self._llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            streaming=stream,
        )

        # 统一会话历史访问器（初始化默认 session）
        self._get_session_history(self._default_session_id)

        # 任务规划器（可选）
        self._task_planner: Optional[TaskPlanner] = None
        if enable_planner:
            self._task_planner = TaskPlanner(
                llm=self._llm,
                registry=self._registry,
            )
            logger.info("TaskPlanner 已启用")

        # 构建默认 ReAct 策略
        self._strategy = self._create_react_strategy()

        # 注册 VisionTool 引用（用于图片处理）
        self._vision_tool = None
        if self._registry.has_tool("vision_tool"):
            self._vision_tool = self._registry.get_tool("vision_tool")

        logger.info(f"MathAgent 初始化完成（model={model}, max_iterations={max_iterations}, planner={enable_planner}）")

    def _create_react_strategy(
        self,
        use_streaming: bool = True,
    ) -> AgentStrategy:
        """
        构建 ReAct 执行策略。

        Args:
            use_streaming: 是否启用打字机效果（默认 True）

        Returns:
            AgentStrategy 实例
        """
        tools = self._registry.get_all_tools() if hasattr(self._registry, "get_all_tools") else []

        thought_recorder = ThoughtRecorder()

        # 构建 ReAct Prompt
        prompt_manager = SystemPromptManager()
        tool_descs = ToolDescriptionGenerator().generate_for_registry(tools)
        prompt_manager.update_tools(tool_descs)
        full_prompt = prompt_manager.get_prompt()

        # 构建 LangChain chain
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=full_prompt),
            ("human", "{input}"),
        ])

        # 流式链（无 StrOutputParser）：用于 astream_events 捕获 token 级别事件
        llm_chain_stream = prompt | self._llm
        # 完整链（有 StrOutputParser）：用于非流式 ainvoke()
        llm_chain_sync = llm_chain_stream | StrOutputParser()

        # 统一使用 ReActStrategy
        logger.info("使用 ReActStrategy（异步流式输出）")
        return ReActStrategy(
            llm_chain=llm_chain_stream,
            llm_chain_sync=llm_chain_sync,
            registry=self._registry,
            tools=tools,
            max_iterations=self._max_iterations,
            thought_recorder=thought_recorder,
        )

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取指定会话的历史记录。"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    # ── 公共 API ────────────────────────────────────────────────────────

    async def process(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        异步处理用户输入（完整结果返回）。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。

        Returns:
            最终答案字符串。
        """
        sid = session_id or self._default_session_id
        context = self._build_context(sid)

        if self._is_image_input(user_input):
            return await self._process_image(user_input, sid, context)

        strategy = self._select_strategy(user_input, sid)
        return await strategy.execute(user_input, sid, context)

    async def stream(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        异步流式处理用户输入，yield 文本片段（打字机效果）。

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。

        Yields:
            输出文本片段（token 级别）。
        """
        sid = session_id or self._default_session_id
        context = self._build_context(sid)

        if self._is_image_input(user_input):
            async for chunk in self._stream_process_image(user_input, sid, context):
                yield chunk
            return

        strategy = self._select_strategy(user_input, sid)
        async for chunk in strategy.stream(user_input, sid, context):
            yield chunk

    async def _stream_process_image(
        self,
        image_path: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        流式处理图片输入。

        流程：
        1. 提示正在识别
        2. 调用 VisionTool 识别图片
        3. 输出识别结果
        4. 调用 ReAct 策略解题
        """
        if not self._registry.has_tool("vision_tool"):
            yield "**【VisionTool 未注册，无法处理图片】**\n\n"
            return

        yield "**【正在识别图片内容...】**\n\n"

        input_data = ToolInput(
            query=image_path,
            parameters={"image_source": image_path},
        )

        result = await self._registry.execute_safe("vision_tool", input_data)

        if not result.success:
            yield f"**【图片识别失败】**: {result.error}\n\n"
            return

        recognized_text = result.result or ""

        yield "**【图片识别结果】**\n\n"
        yield recognized_text
        yield "\n\n---\n\n**【开始解题】**\n\n"

        try:
            async for chunk in self._strategy.stream(recognized_text, session_id, context):
                yield chunk
        except Exception as e:
            logger.error(f"解题过程出错: {e}")
            yield f"\n\n**【解题出错】**: {e}"

    async def stream_multimodal(
        self,
        image_path: str,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式处理多模态输入（图片+文字）。

        将图片识别结果与用户文字说明合并后一起发送给Agent处理，
        确保AI能够获得完整的上下文信息。

        Args:
            image_path: 图片文件路径。
            user_message: 用户的文字说明。
            session_id: 会话ID。

        Yields:
            输出文本片段（token级别）。
        """
        sid = session_id or self._default_session_id
        context = self._build_context(sid)

        if not self._registry.has_tool("vision_tool"):
            yield "**【VisionTool 未注册，无法处理图片】**\n\n"
            return

        yield "**【正在识别图片内容...】**\n\n"

        input_data = ToolInput(
            query=image_path,
            parameters={"image_source": image_path},
        )

        result = await self._registry.execute_safe("vision_tool", input_data)

        if not result.success:
            yield f"**【图片识别失败】**: {result.error}\n\n"
            return

        recognized_text = result.result or ""

        yield "**【图片识别结果】**\n\n"
        yield recognized_text

        if user_message and user_message.strip():
            yield "\n\n---\n\n**【用户问题】**\n\n"
            yield user_message.strip()
            yield "\n\n---\n\n**【开始解题】**\n\n"

            combined_input = f"图片内容：\n{recognized_text}\n\n用户要求：\n{user_message.strip()}\n\n请根据图片内容和用户要求进行解答。"
        else:
            yield "\n\n---\n\n**【开始解题】**\n\n"
            combined_input = recognized_text

        try:
            async for chunk in self._strategy.stream(combined_input, sid, context):
                yield chunk
        except Exception as e:
            logger.error(f"多模态解题过程出错: {e}")
            yield f"\n\n**【解题出错】**: {e}"

    def clear_history(self, session_id: Optional[str] = None) -> None:
        """清空指定会话的对话记忆。"""
        sid = session_id or self._default_session_id
        hist = self._session_histories.get(sid)
        if hist is not None:
            hist.clear()

    def get_thought_recorder(self) -> ThoughtRecorder:
        """获取思维记录器。"""
        if isinstance(self._strategy, ReActStrategy):
            return self._strategy.thought_recorder
        raise RuntimeError("当前策略不支持思维记录")

    @property
    def registry(self) -> ToolRegistry:
        """获取工具注册表。"""
        return self._registry

    @property
    def planner(self) -> Optional[TaskPlanner]:
        """获取任务规划器实例。"""
        return self._task_planner

    def refresh_tools(self) -> None:
        """
        刷新工具列表并重新初始化策略。

        当工具注册表发生变化后调用此方法。
        """
        self._strategy = self._create_react_strategy()
        self._planned_strategy = None
        if self._task_planner is not None:
            self._task_planner.clear_cache()
        logger.info("Agent 工具列表已刷新")

    # ── 策略选择 ────────────────────────────────────────────────────────

    def _select_strategy(
        self,
        user_input: str,
        session_id: str,
    ) -> AgentStrategy:
        """
        根据问题复杂度选择合适的执行策略。

        简单问题 → ReActStrategy（直接边想边做）
        复杂问题 → PlannedStrategy（先规划再执行）

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。

        Returns:
            选定的执行策略。
        """
        # 优先尝试规划器
        if (
            self._task_planner is not None
            and self._task_planner.enabled
            and self._task_planner.should_plan(user_input)
        ):
            logger.info("问题复杂度高，使用 PlannedStrategy")
            return self._get_or_create_planned_strategy()

        logger.info("使用 ReActStrategy（默认）")
        return self._strategy

    _planned_strategy: Optional[PlannedStrategy] = None

    def _get_or_create_planned_strategy(self) -> PlannedStrategy:
        """获取或创建 PlannedStrategy 实例。"""
        if self._planned_strategy is None:
            self._planned_strategy = self._create_planned_strategy()
        return self._planned_strategy

    def _create_planned_strategy(self) -> PlannedStrategy:
        """构建 PlannedStrategy 执行策略。"""
        tools = self._registry.get_all_tools() if hasattr(self._registry, "get_all_tools") else []
        thought_recorder = ThoughtRecorder()

        prompt_manager = SystemPromptManager()
        tool_descs = ToolDescriptionGenerator().generate_for_registry(tools)
        prompt_manager.update_tools(tool_descs)
        full_prompt = prompt_manager.get_prompt()

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=full_prompt),
            ("human", "{input}"),
        ])

        llm_chain = prompt | self._llm | StrOutputParser()

        logger.info("PlannedStrategy 已创建")
        return PlannedStrategy(
            llm_chain=llm_chain,
            registry=self._registry,
            task_planner=self._task_planner,
            thought_recorder=thought_recorder,
        )

    def _build_context(self, session_id: str) -> Dict[str, Any]:
        """构建传递给策略的上下文。"""
        history = self._session_histories.get(session_id)
        return {
            "chat_history": list(history) if history else [],
            "registry": self._registry,
        }

    def _is_image_input(self, user_input: str) -> bool:
        """检查用户输入是否是图片路径。"""
        return any(
            user_input.lower().strip().endswith(ext)
            for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]
        )

    async def _process_image(self, image_path: str, session_id: str, context: Dict[str, Any]) -> str:
        """处理图片输入。"""
        if not self._registry.has_tool("vision_tool"):
            return "VisionTool 未注册，无法处理图片"

        input_data = ToolInput(
            query=image_path,
            parameters={"image_source": image_path},
        )

        result = await self._registry.execute_safe("vision_tool", input_data)

        if result.success:
            recognized_text = result.result or ""
            display_msg = f"【图片识别结果】\n{recognized_text}\n\n"
            answer = await self._strategy.execute(recognized_text, session_id, context)
            return f"{display_msg}{answer}"
        else:
            return f"图片识别失败：{result.error}"


def create_math_agent(
    api_key: str,
    registry: Optional[ToolRegistry] = None,
    model: str = "qwen-max",
    temperature: float = 0,
    max_iterations: int = 5,
    stream: bool = True,
    enable_planner: bool = True,
) -> MathAgent:
    """
    工厂函数：创建 MathAgent 实例。

    这是推荐的创建 Agent 的方式，与原 create_react_agent() 签名兼容。

    Args:
        api_key: API 密钥。
        registry: 工具注册表（可选，默认使用全局注册表）。
        model: 模型名称。
        temperature: 温度参数。
        max_iterations: 最大迭代次数。
        stream: 是否启用流式输出。
        enable_planner: 是否启用任务规划器（默认True）。

    Returns:
        MathAgent 实例。
    """
    return MathAgent(
        api_key=api_key,
        registry=registry,
        model=model,
        temperature=temperature,
        max_iterations=max_iterations,
        stream=stream,
        enable_planner=enable_planner,
    )
