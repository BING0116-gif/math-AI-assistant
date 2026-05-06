"""
MathAgent — 统一的数学解题 Agent。

通过策略模式支持多种执行模式，默认使用 ReAct 完整思维链推理。

架构：
- MathAgent: 统一入口，管理 LLM、Session、工具注册、图片处理
- AgentStrategy: 执行策略抽象基类
- ReActStrategy: 完整的 ReAct 思维链循环，真流式输出（打字机效果）
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

from agent_core.strategies import AgentStrategy, ReActStrategy
from agent_core.thought import ThoughtRecorder
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

        # 构建默认 ReAct 策略
        self._strategy = self._create_react_strategy()

        # 注册 VisionTool 引用（用于图片处理）
        self._vision_tool = None
        if self._registry.has_tool("vision_tool"):
            self._vision_tool = self._registry.get_tool("vision_tool")

        logger.info(f"MathAgent 初始化完成（model={model}, max_iterations={max_iterations}）")

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
        tools = list(self._registry._tools.values()) if hasattr(self._registry, "_tools") else []

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

        # 非流式链，用于获取完整响应
        llm_chain_sync = prompt | self._llm | StrOutputParser()

        # 统一使用 ReActStrategy
        logger.info("使用 ReActStrategy（异步流式输出）")
        return ReActStrategy(
            llm_chain=llm_chain_sync,
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

        return await self._strategy.execute(user_input, sid, context)

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
            # 图片输入：流式输出识别过程
            async for chunk in self._stream_process_image(user_input, sid, context):
                yield chunk
            return

        # 文本输入：直接流式输出
        async for chunk in self._strategy.stream(user_input, sid, context):
            yield chunk

    async def _stream_process_image(
        self,
        image_path: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        流式处理图片输入。

        优化点：
        1. 降低提示信息延迟
        2. 减少识别结果逐字符输出的延迟
        3. 快速进入解题阶段
        """
        if not self._registry.has_tool("vision_tool"):
            yield "【VisionTool 未注册，无法处理图片】"
            return

        start_msg = "【正在识别图片内容...】\n\n"
        for char in start_msg:
            yield char
            await asyncio.sleep(0.002)

        input_data = ToolInput(
            query=image_path,
            parameters={"image_source": image_path},
        )

        result = await self._registry.execute_safe("vision_tool", input_data)

        if not result.success:
            yield f"【图片识别失败：{result.error}】"
            return

        recognized_text = result.result or ""
        header = "【图片识别结果】\n\n"

        for char in header:
            yield char
            await asyncio.sleep(0.002)

        for char in recognized_text:
            yield char
            await asyncio.sleep(0.001)

        yield "\n\n---\n\n**开始解题...**\n\n"

        try:
            async for chunk in self._strategy.stream(recognized_text, session_id, context):
                yield chunk
        except Exception as e:
            logger.error(f"解题过程出错: {e}")
            yield f"\n\n【解题出错：{e}】"

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

    def refresh_tools(self) -> None:
        """
        刷新工具列表并重新初始化策略。

        当工具注册表发生变化后调用此方法。
        """
        self._strategy = self._create_react_strategy()
        logger.info("Agent 工具列表已刷新")

    # ── 私有辅助方法 ─────────────────────────────────────────────────────

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
    )
