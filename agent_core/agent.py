"""
MathAgent — 统一的数学解题 Agent。

使用 LangChainReActStrategy 执行 ReAct 思维链推理。
架构简洁，通过配置对象注入依赖。

架构：
- MathAgent: 统一入口，管理 LLM、Session、工具注册、图片处理
- LangChainReActStrategy: LangChain 原生 ReAct Agent（function calling + 流式输出）
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory

from agent_core.strategies import AgentStrategy, LangChainReActStrategy
from agent_core.thought import ThoughtRecorder
from agent_core.task_planner import (
    TaskPlanner,
    PlannerConfig,
    PlanningContext,
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


# ============================================================================
# 配置数据类 (Configuration Objects)
# ============================================================================

@dataclass
class LLMConfig:
    """LLM 相关配置。"""
    model: str = "qwen-max"
    temperature: float = 0
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class StrategyConfig:
    """执行策略配置。"""
    max_iterations: int = 5
    stream: bool = True


@dataclass
class DynamicParamsConfig:
    """动态参数配置。"""
    enabled: bool = True


@dataclass
class AgentClassifierConfig:
    """分类器配置。"""
    enabled: bool = True
    model: str = "qwen-turbo"
    cache_max_size: int = 2000
    classification_timeout: float = 5.0
    enable_cache: bool = True
    enable_fallback: bool = True


@dataclass
class MathAgentConfig:
    """
    MathAgent 完整配置对象。

    将分散的构造函数参数整合为结构化配置，
    支持按功能分组（LLM / 策略 / 动态参数 / 分类器）。

    Example:
        config = MathAgentConfig(api_key="your-key")
        agent = MathAgent(config)
    """
    api_key: str
    llm: LLMConfig = field(default_factory=LLMConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    dynamic_params: DynamicParamsConfig = field(default_factory=DynamicParamsConfig)
    classifier: AgentClassifierConfig = field(default_factory=AgentClassifierConfig)
    registry: Optional[ToolRegistry] = None

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("api_key 不能为空")


class MathAgent:
    """
    统一的数学解题 Agent。

    使用 LangChainReActStrategy 执行 ReAct 思维链推理，
    所有模式共享：
    - 统一的 LLM 初始化
    - 统一的会话历史管理（InMemoryChatMessageHistory）
    - 统一的图片输入处理（VisionTool）
    - 统一的流式输出基础设施

    Example:
        config = MathAgentConfig(api_key="your-key")
        agent = MathAgent(config)
        async for chunk in agent.stream("求极限"):
            print(chunk, end="")
    """

    def __init__(self, config: MathAgentConfig):
        """
        初始化 MathAgent（使用配置对象）。

        Args:
            config: MathAgentConfig 配置对象，包含所有初始化参数。

        Raises:
            ValueError: 如果 api_key 为空。
        """
        assert config.api_key, "API 密钥必须提供"

        self._config = config
        self._api_key = config.api_key
        self._registry = config.registry or get_registry()
        self._model = config.llm.model
        self._temperature = config.llm.temperature
        self._max_iterations = config.strategy.max_iterations
        self._stream_enabled = config.strategy.stream
        self._base_url = config.llm.base_url
        self._default_session_id = "default"
        self._session_histories: Dict[str, InMemoryChatMessageHistory] = {}
        self._strategy: Optional[AgentStrategy] = None

        # 统一 LLM 实例
        self._llm = ChatOpenAI(
            model=config.llm.model,
            temperature=config.llm.temperature,
            api_key=config.api_key,
            base_url=config.llm.base_url,
            streaming=config.strategy.stream,
        )

        # 动态参数工厂
        self._enable_dynamic_params = config.dynamic_params.enabled
        self._dynamic_llm_factory: Optional[DynamicLLMFactory] = None
        self._init_dynamic_llm_factory(config)

        # 统一会话历史访问器（初始化默认 session）
        self._get_session_history(self._default_session_id)

        # LLM复杂度分类器
        self._enable_classifier = config.classifier.enabled
        self._classifier: Optional[LLMComplexityClassifier] = None
        self._init_classifier(config)

        # 意图分类器（轻量规则匹配，<1ms，零Token消耗）
        self._task_classifier = get_classifier()

        # 构建 LangChainReActStrategy
        self._strategy = self._create_langchain_react_strategy()

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
            f"(model={config.llm.model}, max_iterations={config.strategy.max_iterations})"
        )

    @classmethod
    def create(
        cls,
        api_key: str,
        registry: Optional[ToolRegistry] = None,
        model: str = "qwen-max",
        temperature: float = 0,
        max_iterations: int = 5,
        stream: bool = True,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        enable_dynamic_params: bool = True,
        enable_classifier: bool = True,
        classifier_model: str = "qwen-turbo",
        classifier_config: Optional[dict] = None,
    ) -> "MathAgent":
        """
        向后兼容的工厂方法，支持旧的参数调用方式。

        新代码推荐使用 MathAgent(config) 方式创建。

        Args:
            api_key: API 密钥。
            registry: 工具注册表（可选）。
            model: 模型名称。
            temperature: 温度参数。
            max_iterations: 最大迭代次数。
            stream: 是否启用流式输出。
            base_url: API 基础 URL。
            enable_dynamic_params: 是否启用动态参数。
            enable_classifier: 是否启用分类器。
            classifier_model: 分类器模型。
            classifier_config: 分类器配置字典。

        Returns:
            MathAgent 实例。
        """
        _cfg = classifier_config or {}
        config = MathAgentConfig(
            api_key=api_key,
            registry=registry,
            llm=LLMConfig(
                model=model,
                temperature=temperature,
                base_url=base_url,
            ),
            strategy=StrategyConfig(
                max_iterations=max_iterations,
                stream=stream,
            ),
            dynamic_params=DynamicParamsConfig(
                enabled=enable_dynamic_params,
            ),
            classifier=AgentClassifierConfig(
                enabled=enable_classifier,
                model=classifier_model,
                cache_max_size=_cfg.get("cache_max_size", 2000),
                classification_timeout=_cfg.get("classification_timeout", 5.0),
                enable_cache=_cfg.get("enable_cache", True),
                enable_fallback=_cfg.get("enable_fallback", True),
            ),
        )
        return cls(config)

    def _init_dynamic_llm_factory(self, config: MathAgentConfig) -> None:
        """初始化动态参数工厂。"""
        if not config.dynamic_params.enabled:
            logger.info("动态参数配置已禁用，使用固定LLM配置")
            return

        try:
            self._dynamic_llm_factory = get_dynamic_llm_factory()
            logger.info("使用全局 DynamicLLMFactory 单例")
        except RuntimeError:
            self._dynamic_llm_factory = DynamicLLMFactory(
                api_key=config.api_key,
                base_url=config.llm.base_url,
                model=config.llm.model,
                streaming=config.strategy.stream,
            )
            logger.info("全局单例未初始化，创建独立 DynamicLLMFactory 实例")
        logger.info("动态参数配置已启用")

    def _init_classifier(self, config: MathAgentConfig) -> None:
        """初始化LLM复杂度分类器。"""
        if not config.classifier.enabled:
            logger.info("LLM复杂度分类器已禁用")
            return

        try:
            classifier_llm = ChatOpenAI(
                model=config.classifier.model,
                temperature=0.0,
                api_key=config.api_key,
                base_url=config.llm.base_url,
                streaming=False,
            )

            _classifier_config = ClassifierConfig(
                cache_max_size=config.classifier.cache_max_size,
                enable_cache=config.classifier.enable_cache,
                enable_fallback=config.classifier.enable_fallback,
                classification_timeout=config.classifier.classification_timeout,
            )

            self._classifier = LLMComplexityClassifier(
                llm=classifier_llm,
                config=_classifier_config,
            )

            logger.info(
                f"LLM复杂度分类器已启用 "
                f"(model={config.classifier.model}, "
                f"cache={_classifier_config.cache_max_size}条)"
            )
        except Exception as e:
            logger.warning(f"LLM复杂度分类器初始化失败: {e}")
            self._classifier = None
            self._enable_classifier = False

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

    async def _build_context(
        self,
        session_id: str,
        user_input: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        构建传递给策略的上下文。

        Args:
            session_id: 会话ID
            user_input: 当前用户输入
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
            "user_id": user_id or "anonymous",
        }

        # 注入用户技能画像到上下文
        context["user_skill_instruction"] = ""
        if user_id and self._persistence_facade:
            try:
                profile = await self._persistence_facade.get_profile(user_id)
                if profile and (profile.skills or profile.weak_points):
                    skill_text = self._format_skill_profile_for_llm(profile)
                    context["user_skill_instruction"] = skill_text
                    context["user_skill_profile"] = profile

                    chat_history_dicts.insert(0, {
                        "role": "system",
                        "content": skill_text,
                    })
                    context["chat_history"] = chat_history_dicts

                    logger.info(
                        f"[Skill] 已注入用户技能画像: "
                        f"skills={len(profile.skills)}, "
                        f"weak={len(profile.weak_points)}, "
                        f"cr={profile.correct_rate:.0%}"
                    )
            except Exception as e:
                logger.warning(f"[Skill] 加载用户技能画像失败（非阻塞）: {e}")

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

        rec_diff = int(profile.recommended_difficulty or 3)
        lines.append(f"- 推荐答题难度: T{rec_diff}")

        if profile.error_patterns:
            patterns = [ep.get("pattern", "") for ep in profile.error_patterns[:3] if ep.get("pattern")]
            if patterns:
                lines.append(f"- 常见易错: {', '.join(patterns)} → 回答时主动提醒这些错误")

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
            skill_profile: 用户技能画像指令文本

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

        if skill_profile:
            prompt_manager.update_skill_profile(skill_profile)

        return prompt_manager.get_prompt()

    def _classify_intent(self, user_input: str) -> ClassificationResult:
        """
        对用户输入进行意图分类（T1-T5）。

        使用轻量规则匹配，不消耗LLM Token，执行时间 < 1ms。
        """
        result = self._task_classifier.classify(user_input)
        logger.info(
            f"意图分类: type={result.task_type.value} "
            f"({result.task_type.to_chinese()}), "
            f"confidence={result.confidence:.2f}"
        )
        return result

    def _get_task_params(self, task_type: TaskType) -> LLMParams:
        """根据任务类型获取最佳 LLM 参数配置。"""
        return get_params_for_task(task_type)

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

        # ── 跟进推荐：数学解题类问题自动推荐2道练习题 ──
        follow_up_text = ""
        try:
            from app.services.follow_up_recommender import (
                is_math_problem,
                get_follow_up_recommender,
                format_follow_up_text,
            )
            if is_math_problem(user_input):
                _rec_markers = ["推荐练习", "RAG推荐结果", "推荐题目", "Action: recommend"]
                _text_has_rec = any(m in full_response for m in _rec_markers)
                _tool_used_rec = False
                if hasattr(strategy, '_last_used_tools') and strategy._last_used_tools:
                    _rec_tool_names = {t for t in strategy._last_used_tools if 'recommend' in t.lower()}
                    _tool_used_rec = bool(_rec_tool_names)
                    if _rec_tool_names:
                        logger.info(f"[FOLLOW_UP] 检测到推荐工具调用: {_rec_tool_names}")

                _already_recommended = _text_has_rec or _tool_used_rec
                if _already_recommended:
                    logger.info(f"[FOLLOW_UP] 检测到已有推荐内容，跳过跟进推荐")
                else:
                    effective_user_id = user_id or session_id or "anonymous"
                    recommender = get_follow_up_recommender()
                    follow_up_result = await recommender.recommend(
                        user_input=user_input,
                        user_id=effective_user_id,
                    )
                    follow_up_text = format_follow_up_text(follow_up_result)
                    if follow_up_text:
                        yield follow_up_text
                        full_response += follow_up_text
                        logger.info(f"[FOLLOW_UP] 推荐已追加到回复 | source={follow_up_result.source}")
            else:
                logger.info(f"[FOLLOW_UP] 非解题类问题，跳过推荐")
        except Exception as e:
            logger.warning(f"[FOLLOW_UP] 跟进推荐失败（非致命）: {e}")

        history.add_ai_message(full_response)

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

        将图片识别结果与用户文字说明合并后一起发送给Agent处理。
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
        """清空指定会话的对话记忆。"""
        sid = session_id or self._default_session_id
        hist = self._session_histories.get(sid)
        if hist is not None:
            hist.clear()

    def get_thought_recorder(self):
        """获取思维记录器。"""
        if hasattr(self._strategy, 'thought_recorder'):
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

    def refresh_tools(self) -> None:
        """
        刷新工具列表并重新初始化策略。

        当工具注册表发生变化后调用此方法。
        """
        self._strategy = self._create_langchain_react_strategy()
        logger.info("Agent 工具列表已刷新")

    # ── 策略选择 ────────────────────────────────────────────────────────

    async def _select_strategy(
        self,
        user_input: str,
        session_id: str,
    ) -> AgentStrategy:
        """
        策略选择 — 使用 LangChainReActStrategy 执行。

        决策流程:
            1. 意图分类 (T1-T5, 轻量规则, <1ms)
            2. 如果启用动态参数，使用优化的 LLM 实例
            3. 返回 LangChainReActStrategy
        """
        intent = self._classify_intent(user_input)

        if self._enable_dynamic_params and self._dynamic_llm_factory:
            _optimized_llm = self._dynamic_llm_factory.get_llm(intent.task_type)
            logger.info(
                f"已应用动态参数: type={intent.task_type.value}, "
                f"confidence={intent.confidence:.2f}"
            )

            # 自适应 Token 分配
            if self._classifier is not None:
                try:
                    classification = await self._classifier.classify(user_input)
                    score = classification.score
                    label = ComplexityCategory.get_label(score)
                    logger.info(
                        f"[分类器] score={score}({label}) | "
                        f"method={classification.method} | "
                        f"latency={classification.latency_ms:.0f}ms"
                    )

                    from prompts.dynamic_params import get_adaptive_max_tokens
                    adaptive_tokens = get_adaptive_max_tokens(score, intent.task_type)
                    _optimized_llm = self._dynamic_llm_factory.get_llm(
                        intent.task_type,
                        override_params={"max_tokens": adaptive_tokens},
                    )
                    logger.info(f"自适应Token: score={score} → max_tokens={adaptive_tokens}")
                except Exception as e:
                    logger.warning(f"自适应Token分配失败，使用默认参数: {e}")

            return self._create_langchain_react_strategy(llm=_optimized_llm)

        return self._strategy

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
    enable_dynamic_params: bool = True,
) -> MathAgent:
    """
    工厂函数：创建 MathAgent 实例（向后兼容）。

    Args:
        api_key: API 密钥。
        registry: 工具注册表（可选，默认使用全局注册表）。
        model: 模型名称。
        temperature: 温度参数。
        max_iterations: 最大迭代次数。
        stream: 是否启用流式输出。
        enable_dynamic_params: 是否启用动态参数配置。

    Returns:
        MathAgent 实例。
    """
    config = MathAgentConfig(
        api_key=api_key,
        registry=registry,
        llm=LLMConfig(
            model=model,
            temperature=temperature,
        ),
        strategy=StrategyConfig(
            max_iterations=max_iterations,
            stream=stream,
        ),
        dynamic_params=DynamicParamsConfig(
            enabled=enable_dynamic_params,
        ),
    )
    return MathAgent(config)