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
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agent_core.strategies import AgentStrategy, ReActStrategy, PlannedStrategy, LangChainReActStrategy
from agent_core.thought import ThoughtRecorder
from agent_core.task_planner import (
    TaskPlanner,
    PlannerConfig,
    PlanningContext,
)
from agent_core.context_manager import (
    SmartContextManager,
    ContextBudget,
    ContextStrategy,
    CompressionPriority,
    create_context_manager,
)
from prompts.system_prompt import SystemPromptManager
from prompts.react_prompt import ReActPromptTemplate
from prompts.dynamic_params import (
    TaskClassifier,
    ClassificationResult,
    TaskType,
    LLMParams,
    get_params_for_task,
    get_classifier,
    DynamicLLMFactory,
    get_dynamic_llm_factory,
    init_dynamic_llm_factory,
)
from tools import get_registry, ToolRegistry, BaseTool, ToolInput
from tools.tool_description import ToolDescriptionGenerator
from agent_core.classifier.llm_classifier import (
    LLMComplexityClassifier,
    ClassificationResult as ClassifierClassificationResult,
    ClassifierConfig,
)
from agent_core.classifier.complexity_levels import (
    level_to_strategy,
    ComplexityCategory,
)
from agent_core.memory_persistence import MemoryPersistenceFacade, UserProfile
from app.services.behavior_tracker import LearningBehaviorTracker

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
        enable_128k_context: bool = True,
        context_budget_tokens: int = 128000,
        context_strategy: ContextStrategy = ContextStrategy.HYBRID,
        enable_dynamic_params: bool = True,
        use_langchain_agent: bool = True,
        enable_classifier: bool = True,
        classifier_model: str = "qwen-turbo",
        classifier_config: Optional[dict] = None,
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

        self._enable_dynamic_params = enable_dynamic_params
        self._dynamic_llm_factory: Optional[DynamicLLMFactory] = None
        if enable_dynamic_params:
            try:
                self._dynamic_llm_factory = get_dynamic_llm_factory()
                logger.info("使用全局 DynamicLLMFactory 单例")
            except RuntimeError:
                self._dynamic_llm_factory = DynamicLLMFactory(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    streaming=stream,
                )
                logger.info("全局单例未初始化，创建独立 DynamicLLMFactory 实例")
            logger.info("动态参数配置已启用")
        else:
            logger.info("动态参数配置已禁用，使用固定LLM配置")

        # 统一会话历史访问器（初始化默认 session）
        self._get_session_history(self._default_session_id)

        # ── 🆕 新增：128K 上下文记忆管理系统 ──
        self._enable_128k_context = enable_128k_context
        self._context_budget_tokens = context_budget_tokens
        self._context_strategy = context_strategy
        self._context_managers: Dict[str, SmartContextManager] = {}
        
        if enable_128k_context:
            logger.info(
                f"[OK] 128K上下文记忆系统已启用: "
                f"budget={context_budget_tokens} tokens, "
                f"strategy={context_strategy.value}"
            )
        else:
            logger.info("[WARN] 128K上下文记忆系统已禁用，使用传统模式")

        # 任务规划器（可选）
        self._task_planner: Optional[TaskPlanner] = None
        if enable_planner:
            self._task_planner = TaskPlanner(
                llm=self._llm,
                registry=self._registry,
            )
            logger.info("TaskPlanner 已启用")

        # ── 🆕 新增: LLM复杂度分类器 ──
        self._enable_classifier = enable_classifier
        self._classifier: Optional[LLMComplexityClassifier] = None

        if enable_classifier:
            try:
                classifier_llm = ChatOpenAI(
                    model=classifier_model,
                    temperature=0.0,
                    api_key=api_key,
                    base_url=base_url,
                    streaming=False,
                )

                _cfg = classifier_config or {}
                _classifier_config = ClassifierConfig(
                    cache_max_size=_cfg.get("cache_max_size", 2000),
                    enable_cache=_cfg.get("enable_cache", True),
                    enable_fallback=_cfg.get("enable_fallback", True),
                    classification_timeout=_cfg.get("classification_timeout", 5.0),
                )

                self._classifier = LLMComplexityClassifier(
                    llm=classifier_llm,
                    config=_classifier_config,
                )

                logger.info(
                    f"[OK] LLM复杂度分类器已启用 "
                    f"(model={classifier_model}, "
                    f"cache={_classifier_config.cache_max_size}条)"
                )
            except Exception as e:
                logger.warning(f"[WARN] LLM复杂度分类器初始化失败: {e}，将使用原有策略路由")
                self._classifier = None
                self._enable_classifier = False
        else:
            logger.info("[WARN] LLM复杂度分类器已禁用，使用原有策略路由")

        # 意图分类器（轻量规则匹配，<1ms，零Token消耗）
        self._task_classifier = get_classifier()

        self._use_langchain = use_langchain_agent

        # 构建默认 ReAct 策略
        if self._use_langchain:
            self._strategy = self._create_langchain_react_strategy()
        else:
            self._strategy = self._create_react_strategy()

        # 注册 VisionTool 引用（用于图片处理）
        self._vision_tool = None
        if self._registry.has_tool("vision_tool"):
            self._vision_tool = self._registry.get_tool("vision_tool")

        self._persistence_facade = MemoryPersistenceFacade()
        self._behavior_tracker = LearningBehaviorTracker()
        self._behavior_tracker.set_llm_classifier(self._llm)
        logger.info("MemoryPersistenceFacade + BehaviorTracker + LLM 已初始化")

        logger.info(
            f"MathAgent 初始化完成"
            f"(model={model}, max_iterations={max_iterations}, "
            f"planner={enable_planner}, "
            f"agent={'langchain' if self._use_langchain else 'custom'}, "
            f"context_128k={'[OK]' if enable_128k_context else '[X]'})"
        )

    def _create_react_strategy(
        self,
        use_streaming: bool = True,
        llm: Optional[ChatOpenAI] = None,
    ) -> AgentStrategy:
        _llm = llm or self._llm
        tools = self._registry.get_all_tools() if hasattr(self._registry, "get_all_tools") else []

        thought_recorder = ThoughtRecorder()

        full_prompt = self._build_system_prompt(tools)

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=full_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

        llm_chain_stream = prompt | _llm
        llm_chain_sync = llm_chain_stream | StrOutputParser()

        logger.info("使用 ReActStrategy（异步流式输出 + v3.0四层Prompt架构）")
        return ReActStrategy(
            llm_chain=llm_chain_stream,
            llm_chain_sync=llm_chain_sync,
            registry=self._registry,
            tools=tools,
            max_iterations=self._max_iterations,
            thought_recorder=thought_recorder,
        )

    def _create_langchain_react_strategy(self, llm: Optional[ChatOpenAI] = None) -> LangChainReActStrategy:
        _llm = llm or self._llm
        full_prompt = self._build_system_prompt()

        logger.info("使用 LangChainReActStrategy（原生function calling + 流式输出）")
        return LangChainReActStrategy(
            llm=_llm,
            registry=self._registry,
            system_prompt=full_prompt,
            max_iterations=self._max_iterations,
        )

    def _create_strategy_with_llm(self, llm: ChatOpenAI) -> AgentStrategy:
        if self._use_langchain:
            return self._create_langchain_react_strategy(llm=llm)
        else:
            return self._create_react_strategy(llm=llm)

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取指定会话的历史记录。"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    def clear_session(self, session_id: str) -> None:
        """清除指定会话的历史记录。"""
        hist = self._session_histories.pop(session_id, None)
        if hist:
            hist.clear()

    # ── 🆕 新增：128K上下文管理器访问器 ──

    def _get_or_create_context_manager(
        self, 
        session_id: str,
        user_id: Optional[str] = None,
    ) -> SmartContextManager:
        """
        获取或创建指定会话的SmartContextManager。
        
        每个session_id对应一个独立的上下文管理器实例，
        确保不同用户的对话历史相互隔离。
        
        Args:
            session_id: 会话ID
            user_id: 用户ID（可选，用于未来扩展）
            
        Returns:
            该会话的SmartContextManager实例
        """
        if session_id not in self._context_managers:
            budget = ContextBudget(total_tokens=self._context_budget_tokens)
            
            self._context_managers[session_id] = create_context_manager(
                session_id=session_id,
                total_budget_tokens=self._context_budget_tokens,
                strategy=self._context_strategy,
                max_history_turns=20,
                summarize_threshold=0.8,
                importance_scoring_enabled=True,
                auto_optimize=True,
            )
            
            logger.debug(
                f"[OK] 为session '{session_id}' 创建新的ContextManager"
            )
        
        return self._context_managers[session_id]

    async def _build_context(
        self, 
        session_id: str, 
        user_input: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        构建传递给策略的增强上下文。
        
        新增功能：
        1. 如果启用128K模式，使用SmartContextManager管理对话历史
        2. 构建符合OpenAI格式的完整LLM上下文（≤128K tokens）
        3. 提供详细的统计和监控信息
        
        Args:
            session_id: 会话ID
            user_input: 当前用户输入（用于记录到上下文）
            user_id: 用户ID（可选）
            
        Returns:
            包含完整上下文信息的字典
        """
        history = self._session_histories.get(session_id)
        
        chat_history_dicts = []
        if history:
            raw_items = list(history)
            for item in raw_items:
                if isinstance(item, tuple) and len(item) == 2:
                    inner_messages = item[1] if isinstance(item[1], list) else [item[1]]
                else:
                    inner_messages = [item]
                
                for msg in inner_messages:
                    msg_type = getattr(msg, 'type', None)
                    content = getattr(msg, 'content', '')
                    if msg_type in ('human', 'user'):
                        chat_history_dicts.append({"role": "user", "content": content})
                    elif msg_type in ('ai', 'assistant'):
                        chat_history_dicts.append({"role": "assistant", "content": content})
        
        context = {
            "chat_history": chat_history_dicts,
            "registry": self._registry,
            "user_id": user_id or "anonymous",  # ← 确保user_id在context中
        }

        # ── 🆕 注入用户技能画像到上下文（P0: LLM 感知用户水平）──
        context["user_skill_instruction"] = ""
        if user_id and self._persistence_facade:
            try:
                profile = await self._persistence_facade.get_profile(user_id)
                if profile and (profile.skills or profile.weak_points):
                    skill_text = self._format_skill_profile_for_llm(profile)
                    context["user_skill_instruction"] = skill_text
                    context["user_skill_profile"] = profile

                    # 非128K模式：将技能指令注入 chat_history 开头（作为系统消息）
                    # 128K模式：在下方注入到 System Prompt 中
                    if not self._enable_128k_context:
                        chat_history_dicts.insert(0, {
                            "role": "system",
                            "content": skill_text,
                        })
                        context["chat_history"] = chat_history_dicts

                    logger.info(
                        f"[Skill] 已注入用户技能画像: "
                        f"skills={len(profile.skills)}, "
                        f"weak={len(profile.weak_points)}, "
                        f"cr={profile.correct_rate:.0%}, "
                        f"mode={'128K' if self._enable_128k_context else 'chat_history'}"
                    )
            except Exception as e:
                logger.warning(f"[Skill] 加载用户技能画像失败（非阻塞）: {e}")
        
        # ── 🆕 集成128K上下文管理 ──
        if self._enable_128k_context and user_input:
            try:
                ctx_mgr = self._get_or_create_context_manager(session_id, user_id)
                
                # 将用户输入添加到上下文记忆系统
                add_success = ctx_mgr.add_message(
                    role="user",
                    content=user_input,
                    metadata={
                        "user_id": user_id or "anonymous",
                        "timestamp": time.time(),
                        "source": "user_input",
                    },
                )
                
                if not add_success:
                    logger.warning(
                        f"[WARN] Session {session_id}: 无法将用户消息添加到128K上下文"
                        "(可能已达到容量上限)"
                    )
                
                # 构建完整的LLM上下文（严格≤128K）
                # P0：将用户技能画像通过 System Prompt 模板注入
                skill_instruction = context.get("user_skill_instruction", "")
                system_prompt = self._get_system_prompt(skill_profile=skill_instruction)

                if skill_instruction:
                    logger.debug(f"[Skill] 已注入技能指令到 System Prompt ({len(skill_instruction)}字符)")
                
                llm_messages = ctx_mgr.build_llm_context(
                    system_prompt=system_prompt,
                    include_metadata=True,
                )
                
                # 提取元数据（最后一个消息是__metadata__格式）
                context_metadata = {}
                if llm_messages and llm_messages[-1].get("role") == "__metadata__":
                    import json
                    meta_msg = llm_messages.pop()
                    try:
                        context_metadata = json.loads(meta_msg["content"])
                    except Exception:
                        pass
                
                # 注入增强的上下文信息
                context["llm_messages"] = llm_messages  # 替代chat_history
                context["context_128k_enabled"] = True
                context["context_stats"] = {
                    "total_tokens": ctx_mgr.get_total_tokens_used(),
                    "utilization_rate": ctx_mgr.get_utilization_rate(),
                    "message_count": ctx_mgr.get_message_count(),
                    "turn_count": ctx_mgr.get_turn_count(),
                    **context_metadata,
                }
                
                logger.debug(
                    f"[OK] 128K上下文构建完成: "
                    f"session={session_id}, "
                    f"tokens={ctx_mgr.get_total_tokens_used()}/128000, "
                    f"messages={len(llm_messages)}"
                )
                
            except Exception as e:
                logger.error(f"[ERR] 128K上下文构建失败，回退到传统模式: {e}")
                context["context_128k_enabled"] = False
                context["context_error"] = str(e)
        else:
            context["context_128k_enabled"] = False
        
        return context

    @staticmethod
    def _format_skill_profile_for_llm(profile) -> str:
        """
        将用户技能画像格式化为 LLM 可理解的指令文本。

        设计原则：
        - 紧凑（<300 tokens），不浪费上下文窗口
        - 可操作：告诉 LLM 如何根据技能水平调整行为
        - 容错：数据不足时降级为通用指令
        """
        lines = ["【用户学习档案】(基于历史学习数据分析)"]

        # 学习水平判定
        cr = profile.correct_rate or 0
        if cr >= 0.85:
            level, level_hint = "优秀", "可挑战高难度，引入竞赛/拓展内容"
        elif cr >= 0.7:
            level, level_hint = "良好", "保持当前节奏，适当增加深度"
        elif cr >= 0.5:
            level, level_hint = "中等", "注重基础巩固，循序渐进"
        elif cr >= 0.3:
            level, level_hint = "初学", "从基础概念讲起，多用例子"
        else:
            level, level_hint = "入门", "用最简单的语言，一步步引导"

        lines.append(f"- 当前水平: {level} (正确率 {cr:.0%}) → {level_hint}")

        # 薄弱知识点（最关键的信息）
        weak_skills = []
        if profile.weak_points:
            for wp in profile.weak_points[:4]:
                cat = wp.get("category", "")
                m = wp.get("mastery", 0)
                weak_skills.append(f"{cat}({m:.0%})")
        if profile.skills:
            for s in sorted(profile.skills, key=lambda x: x.get("mastery_level", 0))[:4]:
                m = s.get("mastery_level", 0)
                name = s.get("skill_code", s.get("display_name", ""))
                st = s.get("status", "")
                if m < 0.35 and st != "mastered":
                    weak_skills.append(f"{name}({m:.0%})")

        if weak_skills:
            unique_weak = list(dict.fromkeys(weak_skills))[:5]
            lines.append(f"- 薄弱知识点: {', '.join(unique_weak)} → 请重点讲解基础概念，多给示例和类比")

        # 已掌握知识点
        strong_skills = []
        if profile.strong_points:
            strong_skills = list(profile.strong_points)[:3]
        if profile.skills:
            for s in sorted(profile.skills, key=lambda x: x.get("mastery_level", 0), reverse=True)[:3]:
                if s.get("status") == "mastered":
                    name = s.get("skill_code", s.get("display_name", ""))
                    if name not in strong_skills:
                        strong_skills.append(name)

        if strong_skills:
            lines.append(f"- 已掌握: {', '.join(strong_skills[:3])} → 可适当提高深度，引入关联知识")

        # 推荐难度
        rec_diff = int(profile.recommended_difficulty or 3)
        lines.append(f"- 推荐答题难度: T{rec_diff}")

        # 易错模式
        if profile.error_patterns:
            patterns = [ep.get("pattern", "") for ep in profile.error_patterns[:3] if ep.get("pattern")]
            if patterns:
                lines.append(f"- 常见易错: {', '.join(patterns)} → 回答时主动提醒这些错误")

        # 认知风格（如果有）
        if profile.cognitive_style:
            style_hint = profile.cognitive_style.get("style_hint", "")
            if style_hint:
                lines.append(f"- 学习偏好: {style_hint}")

        return "\n".join(lines)

    def _build_system_prompt(
        self,
        tools: Optional[List[BaseTool]] = None,
        style: str = "详细",
        skill_profile: str = "",
    ) -> str:
        """
        构建完整的 System Prompt（四层架构 + 工具描述 + ReAct指令 + 教学风格 + 技能画像）。

        Args:
            tools: 工具列表，如果为 None 则使用注册表中的所有工具
            style: 教学风格（"详细"/"简洁"/"直观"/"严谨"）
            skill_profile: 用户技能画像指令文本（P0 注入）

        Returns:
            完整的 System Prompt 字符串
        """
        if tools is None:
            tools = (
                self._registry.get_all_tools()
                if hasattr(self._registry, 'get_all_tools')
                else []
            )

        prompt_manager = SystemPromptManager()
        tool_descs = ToolDescriptionGenerator().generate_for_registry(tools)
        prompt_manager.update_tools(tool_descs)

        react_instruction = ReActPromptTemplate.build_instruction(
            tool_names=[t.name for t in tools] if tools else []
        )
        prompt_manager.update_react_instruction(react_instruction)
        prompt_manager.update_style_instruction(style)

        # P0：注入用户技能画像到 System Prompt 模板
        if skill_profile:
            prompt_manager.update_skill_profile(skill_profile)

        return prompt_manager.get_prompt()

    def _get_system_prompt(self, skill_profile: str = "") -> str:
        """获取当前System Prompt。"""
        return self._build_system_prompt(skill_profile=skill_profile)

    def _classify_intent(self, user_input: str) -> ClassificationResult:
        """
        对用户输入进行意图分类（T1-T5）。

        使用轻量规则匹配，不消耗LLM Token，执行时间 < 1ms。

        Args:
            user_input: 用户输入文本。

        Returns:
            ClassificationResult 包含任务类型和置信度。
        """
        result = self._task_classifier.classify(user_input)
        logger.info(
            f"意图分类: type={result.task_type.value} "
            f"({result.task_type.to_chinese()}), "
            f"confidence={result.confidence:.2f}"
        )
        return result

    def _get_task_params(self, task_type: TaskType) -> LLMParams:
        """
        根据任务类型获取最佳 LLM 参数配置。

        Args:
            task_type: 任务类型。

        Returns:
            LLMParams 参数配置。
        """
        return get_params_for_task(task_type)

    def save_assistant_response_to_context(
        self,
        session_id: str,
        response_text: str,
        metadata: Optional[Dict] = None,
    ):
        """
        将Assistant的回复保存到128K上下文记忆中。
        
        应在策略执行完成后调用此方法，确保对话历史的完整性。
        
        Args:
            session_id: 会话ID
            response_text: AI的回复文本
            metadata: 可选的元数据（如使用的策略、迭代次数等）
        """
        if not self._enable_128k_context:
            return
        
        ctx_mgr = self._context_managers.get(session_id)
        if not ctx_mgr:
            return
        
        success = ctx_mgr.add_message(
            role="assistant",
            content=response_text,
            priority=CompressionPriority.NORMAL,  # 普通优先级，可被压缩
            metadata={
                **(metadata or {}),
                "source": "assistant_response",
                "model": self._model,
                "timestamp": time.time(),
            },
        )
        
        if success:
            logger.debug(
                f"[OK] Assistant回复已保存到128K上下文: "
                f"session={session_id}, length={len(response_text)}"
            )
        else:
            logger.warning(
                f"[WARN] 无法保存Assistant回复到128K上下文: "
                f"session={session_id}"
            )

    # ── 公共 API ────────────────────────────────────────────────────────

    async def process(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        sid = session_id or self._default_session_id

        history = self._get_session_history(sid)
        history.add_user_message(user_input)

        context = await self._build_context(sid, user_input=user_input, user_id=user_id)

        if self._is_image_input(user_input):
            return await self._process_image(user_input, sid, context)

        strategy = await self._select_strategy(user_input, sid)
        result = await strategy.execute(user_input, sid, context)
        
        history.add_ai_message(result)
        
        self.save_assistant_response_to_context(
            session_id=sid,
            response_text=result,
            metadata={"strategy": "react", "mode": "process"},
        )
        
        if self._persistence_facade:
            effective_user_id = user_id or session_id or "anonymous"
            try:
                tracked = self._behavior_tracker.track(
                    user_id=effective_user_id,
                    raw_input=user_input,
                    source="chat",
                    metadata={
                        "response_length": len(result),
                        "strategy": type(strategy).__name__,
                        "mode": "process",
                    },
                )
                await self._persistence_facade.record_event(
                    user_id=effective_user_id, event_data=tracked
                )
            except Exception as e:
                logger.warning(f"行为追踪记录失败（非致命）: {e}")
        
        return result

    async def stream(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        sid = session_id or self._default_session_id

        history = self._get_session_history(sid)
        history.add_user_message(user_input)

        context = await self._build_context(sid, user_input=user_input, user_id=user_id)

        if self._is_image_input(user_input):
            async for chunk in self._stream_process_image(user_input, sid, context):
                yield chunk
            return

        strategy = await self._select_strategy(user_input, sid)
        
        logger.info(f"[AGENT-STREAM] 策略选择完成，开始流式执行: input='{user_input[:30]}...'")
        
        chunks = []
        async for chunk in strategy.stream(user_input, sid, context):
            if chunk:
                yield chunk
                chunks.append(chunk)
        
        full_response = "".join(chunks)
        logger.info(f"[AGENT-STREAM] 流式执行完成: total_chunks={len(chunks)}, total_len={len(full_response)}")
        
        history.add_ai_message(full_response)
        
        self.save_assistant_response_to_context(
            session_id=sid,
            response_text=full_response,
            metadata={"strategy": "react", "mode": "stream"},
        )
        
        if self._persistence_facade:
            effective_user_id = user_id or session_id or "anonymous"
            try:
                tracked = self._behavior_tracker.track(
                    user_id=effective_user_id,
                    raw_input=user_input,
                    source="chat",
                    metadata={
                        "response_length": len(full_response),
                        "strategy": type(strategy).__name__,
                        "mode": "stream",
                    },
                )
                await self._persistence_facade.record_event(
                    user_id=effective_user_id, event_data=tracked
                )
            except Exception as e:
                logger.warning(f"流式行为追踪记录失败（非致命）: {e}")

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
        4. 通过分类器路由选择最优策略解题
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
            strategy = await self._select_strategy(recognized_text, session_id)
            logger.info(f"[图片识别] 分类器路由完成，使用策略解题")
            async for chunk in strategy.stream(recognized_text, session_id, context):
                yield chunk
        except Exception as e:
            logger.error(f"解题过程出错: {e}")
            yield f"\n\n**【解题出错】**: {e}"

    async def stream_multimodal(
        self,
        image_path: str,
        user_message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式处理多模态输入（图片+文字）。

        将图片识别结果与用户文字说明合并后一起发送给Agent处理，
        确保AI能够获得完整的上下文信息。
        通过分类器路由选择最优策略进行解题。

        Args:
            image_path: 图片文件路径。
            user_message: 用户的文字说明。
            session_id: 会话ID。

        Yields:
            输出文本片段（token级别）。
        """
        sid = session_id or self._default_session_id
        context = await self._build_context(sid)

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
            strategy = await self._select_strategy(combined_input, sid)
            logger.info(f"[多模态] 分类器路由完成，使用策略解题")
            async for chunk in strategy.stream(combined_input, sid, context):
                yield chunk
        except Exception as e:
            logger.error(f"多模态解题过程出错: {e}")
            yield f"\n\n**【解题出错】**: {e}"

        if self._persistence_facade:
            effective_user_id = user_id or session_id or "anonymous"
            try:
                tracked = self._behavior_tracker.track(
                    user_id=effective_user_id,
                    raw_input=user_message or "(纯图片)",
                    source="chat_multimodal",
                    metadata={"has_image": bool(image_path)},
                )
                await self._persistence_facade.record_event(
                    user_id=effective_user_id, event_data=tracked
                )
            except Exception as e:
                logger.warning(f"多模态行为追踪记录失败（非致命）: {e}")

    def clear_history(self, session_id: Optional[str] = None) -> None:
        """清空指定会话的对话记忆（包括128K上下文）。"""
        sid = session_id or self._default_session_id
        
        # 清理传统历史
        hist = self._session_histories.get(sid)
        if hist is not None:
            hist.clear()
        
        # 🆕 清理128K上下文管理器
        if sid in self._context_managers:
            self._context_managers[sid].clear(preserve_critical=False)
            del self._context_managers[sid]
            logger.info(f"[CLEAN] 已清空session '{sid}'的128K上下文记忆")

    def get_thought_recorder(self):
        """获取思维记录器。"""
        if self._use_langchain:
            if hasattr(self._strategy, 'thought_recorder'):
                return self._strategy.thought_recorder
        else:
            if isinstance(self._strategy, ReActStrategy):
                return self._strategy.thought_recorder
        raise RuntimeError("当前策略不支持思维记录")

    @property
    def registry(self) -> ToolRegistry:
        """获取工具注册表。"""
        return self._registry

    @property
    def dynamic_llm_factory(self) -> Optional[DynamicLLMFactory]:
        """获取动态LLM工厂实例。"""
        return self._dynamic_llm_factory

    @property
    def planner(self) -> Optional[TaskPlanner]:
        """获取任务规划器实例。"""
        return self._task_planner
    
    def get_context_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取128K上下文记忆的统计信息。
        
        Args:
            session_id: 会话ID（默认使用default session）
            
        Returns:
            包含详细统计数据的字典，如果128K未启用则返回空字典
        """
        if not self._enable_128k_context:
            return {"enabled": False, "reason": "128K上下文未启用"}
        
        sid = session_id or self._default_session_id
        ctx_mgr = self._context_managers.get(sid)
        
        if not ctx_mgr:
            return {
                "enabled": True,
                "session_id": sid,
                "status": "not_initialized",
                "message": "该session尚未有任何交互",
            }
        
        stats = ctx_mgr.get_stats()
        
        # 添加额外的有用信息
        stats["session_count"] = len(self._context_managers)
        stats["total_tokens_budget"] = 128000
        stats["remaining_tokens"] = 128000 - stats["total_tokens"]
        stats["utilization_percentage"] = f"{stats['utilization_rate']*100:.1f}%"
        
        # 完整性校验结果
        all_ok, failed_ids = ctx_mgr.verify_all_integrity()
        stats["integrity_check"] = {
            "all_passed": all_ok,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids[:5],  # 最多显示5个
        }
        
        return stats

    def refresh_tools(self) -> None:
        """
        刷新工具列表并重新初始化策略。

        当工具注册表发生变化后调用此方法。
        """
        if self._use_langchain:
            self._strategy = self._create_langchain_react_strategy()
        else:
            self._strategy = self._create_react_strategy()
        self._planned_strategy = None
        if self._task_planner is not None:
            self._task_planner.clear_cache()
        logger.info("Agent 工具列表已刷新")

    # ── 策略选择 ────────────────────────────────────────────────────────

    async def _select_strategy(
        self,
        user_input: str,
        session_id: str,
    ) -> AgentStrategy:
        """
        智能策略选择 — 优先使用LLM分类器，降级使用规则匹配。

        决策流程:
            1. 意图分类 (T1-T5, 轻量规则, <1ms)
            2. LLM复杂度分类 (qwen-turbo, ~200ms)  ← 新增
            3. 根据复杂度分数选择策略:
               - 分数 1-3 → ReActStrategy
               - 分数 4-5 → PlannedStrategy
            4. 如果分类器不可用，降级到原有 TaskPlanner 逻辑

        Args:
            user_input: 用户输入。
            session_id: 会话 ID。

        Returns:
            选定的执行策略。
        """
        intent = self._classify_intent(user_input)

        dynamic_strategy: Optional[AgentStrategy] = None
        _optimized_llm: Optional[ChatOpenAI] = None

        if self._enable_dynamic_params and self._dynamic_llm_factory:
            _optimized_llm = self._dynamic_llm_factory.get_llm(intent.task_type)
            dynamic_strategy = self._create_strategy_with_llm(_optimized_llm)

            logger.info(
                f"已应用动态参数: type={intent.task_type.value}, "
                f"confidence={intent.confidence:.2f}"
            )

        # ── 🆕 优先使用LLM分类器 ──
        if self._classifier is not None:
            try:
                classification = await self._classifier.classify(user_input)

                score = classification.score
                strategy_name = classification.strategy
                label = ComplexityCategory.get_label(score)

                logger.info(
                    f"[分类器路由] score={score}({label}) "
                    f"→ strategy={strategy_name} | "
                    f"method={classification.method} | "
                    f"confidence={classification.confidence:.2f} | "
                    f"latency={classification.latency_ms:.0f}ms | "
                    f"intent={intent.task_type.to_chinese()}"
                )

                # ── 自适应 Token 分配：根据复杂度评分调整 max_tokens ──
                if self._enable_dynamic_params and self._dynamic_llm_factory:
                    try:
                        from prompts.dynamic_params import get_adaptive_max_tokens
                        adaptive_tokens = get_adaptive_max_tokens(score, intent.task_type)
                        _optimized_llm = self._dynamic_llm_factory.get_llm(
                            intent.task_type,
                            override_params={"max_tokens": adaptive_tokens},
                        )
                        dynamic_strategy = self._create_strategy_with_llm(_optimized_llm)
                        logger.info(f"自适应Token: score={score} → max_tokens={adaptive_tokens}")
                    except Exception as e:
                        logger.warning(f"自适应Token分配失败，使用默认参数: {e}")

                if strategy_name == "planned":
                    if self._task_planner is not None and self._task_planner.enabled:
                        logger.info(f"[OK] 使用 PlannedStrategy (score={score}, {label})")
                        return self._get_or_create_planned_strategy(llm=_optimized_llm)

                    logger.warning("分类器建议 Planned，但规划器未启用，回退到 ReAct")
                    return dynamic_strategy or self._strategy

                else:
                    logger.info(f"[OK] 使用 ReActStrategy (score={score}, {label})")
                    return dynamic_strategy or self._strategy

            except Exception as e:
                logger.error(
                    f"[ERR] LLM分类器异常: {type(e).__name__}: {e}，"
                    f"降级到原有逻辑"
                )

        # ── 降级: 原有 TaskPlanner.should_plan() 逻辑 ──
        logger.info(
            f"使用原有策略路由 "
            f"(意图={intent.task_type.to_chinese()}, "
            f"confidence={intent.confidence:.2f})"
        )

        if (
            self._task_planner is not None
            and self._task_planner.enabled
            and self._task_planner.should_plan(user_input)
        ):
            logger.info(
                f"TaskPlanner判断复杂度高 → 使用 PlannedStrategy "
                f"(意图={intent.task_type.to_chinese()})"
            )
            return self._get_or_create_planned_strategy(llm=_optimized_llm)

        logger.info(
            f"使用 ReActStrategy (意图={intent.task_type.to_chinese()}, "
            f"confidence={intent.confidence:.2f})"
        )
        return dynamic_strategy or self._strategy

    _planned_strategy: Optional[PlannedStrategy] = None

    def _get_or_create_planned_strategy(self, llm: Optional[ChatOpenAI] = None) -> PlannedStrategy:
        if llm is not None:
            return self._create_planned_strategy(llm=llm)
        if self._planned_strategy is None:
            self._planned_strategy = self._create_planned_strategy()
        return self._planned_strategy

    def _create_planned_strategy(self, llm: Optional[ChatOpenAI] = None) -> PlannedStrategy:
        """构建 PlannedStrategy 执行策略。

        创建包含完整对话历史的 LLM chain，
        确保子任务能够访问上下文信息。
        """
        _llm = llm or self._llm
        tools = self._registry.get_all_tools() if hasattr(self._registry, "get_all_tools") else []
        thought_recorder = ThoughtRecorder()

        prompt_manager = SystemPromptManager()
        tool_descs = ToolDescriptionGenerator().generate_for_registry(tools)
        prompt_manager.update_tools(tool_descs)
        react_instruction = ReActPromptTemplate.build_instruction(
            tool_names=[t.name for t in tools] if tools else []
        )
        prompt_manager.update_react_instruction(react_instruction)
        full_prompt = prompt_manager.get_prompt()

        # 完整版 prompt：包含 system + chat_history + user
        # 确保子任务能访问对话历史上下文
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=full_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ])

        llm_chain = prompt | _llm | StrOutputParser()

        logger.info("PlannedStrategy 已创建（包含完整chat_history支持）")
        return PlannedStrategy(
            llm_chain=llm_chain,
            registry=self._registry,
            task_planner=self._task_planner,
            thought_recorder=thought_recorder,
        )

    def _is_image_input(self, user_input: str) -> bool:
        """检查用户输入是否是图片路径。"""
        return any(
            user_input.lower().strip().endswith(ext)
            for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]
        )

    async def _process_image(self, image_path: str, session_id: str, context: Dict[str, Any]) -> str:
        """处理图片输入，通过分类器路由选择最优策略解题。"""
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
            strategy = await self._select_strategy(recognized_text, session_id)
            logger.info(f"[图片识别] 分类器路由完成，使用策略解题")
            answer = await strategy.execute(recognized_text, session_id, context)
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
    enable_dynamic_params: bool = True,
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
        enable_dynamic_params: 是否启用动态参数配置（默认True）。

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
        enable_dynamic_params=enable_dynamic_params,
    )
