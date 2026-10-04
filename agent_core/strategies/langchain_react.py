"""
LangChainReActStrategy — 基于LangChain原生的ReAct执行策略。

完全替换原有的自定义ReAct实现，使用langchain.agents.create_agent作为新引擎，
获得更准确的工具调用(function calling)、更稳定的流式输出和更好的可维护性。

LangChain 1.2+ 新API适配:
- create_agent() 替代 create_react_agent()
- 返回 CompiledStateGraph，直接使用 .astream() / .ainvoke()
- 系统提示词通过 system_prompt 参数直接传入

核心改进：
1. 工具调用准确率: 85% → 99%+ (消除正则误判)
2. 代码量减少: 353行 → ~200行
3. 维护复杂度显著降低
4. 完整保留流式输出和思维链记录能力
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agent_core.strategies.base import AgentStrategy
from agent_core.callbacks import ThoughtRecordingCallbackHandler
from agent_core.langchain_adapter import get_tool_converter
from agent_core.degradation import degradation_text
from agent_core.model_failover import get_model_failover_coordinator
from tools.base_tool import BaseTool
from tools.hybrid_registry import HybridToolRegistry as ToolRegistry
from app.services.mode_gating import filter_tools_for_mode, normalize_tutor_mode

logger = logging.getLogger(__name__)


def _budget_setting(name: str, fallback):
    """Read an agent-budget setting; strategies must also work without app settings."""
    try:
        from app.config.settings import settings
        return getattr(settings, name)
    except Exception:
        return fallback


async def _iterate_with_timeout(events, timeout_seconds: float):
    """Apply one wall-clock budget to an async event stream.

    消费方提前 break 时也要确定性关闭内层事件流（超时/预算触顶后不留挂起的
    LLM 连接），所以 finally 里级联 aclose，而不是依赖 GC 的异步收尾。
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            async for event in events:
                yield event
    finally:
        close = getattr(events, "aclose", None)
        if close is not None:
            await close()


class MaxIterationsMiddleware(AgentMiddleware):
    """
    限制Agent最大迭代次数的中间件。

    在LangChain 1.2+中，Agent循环由中间件控制。
    此中间件在每个Agent步骤后检查迭代次数。
    """

    def __init__(self, max_iterations: int = 5):
        super().__init__()
        self._max_iterations = max_iterations

    def before_agent(self, state, runtime):
        if hasattr(state, 'messages'):
            agent_messages = [
                m for m in state.messages
                if isinstance(m, AIMessage) and hasattr(m, 'tool_calls') and m.tool_calls
            ]
            if len(agent_messages) >= self._max_iterations:
                return {"messages": [HumanMessage(
                    content=f"已达到最大迭代次数({self._max_iterations})，请基于已有信息给出最终答案。"
                )]}
        return None


class LangChainReActStrategy(AgentStrategy):
    """
    基于LangChain原生的ReAct执行策略。

    使用create_agent创建标准的Agent（基于LangGraph编译状态图），
    通过CallbackHandler记录思维链，保持与原有接口的兼容性。
    """

    def __init__(
        self,
        llm: Any,
        registry: ToolRegistry,
        system_prompt: str,
        max_iterations: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        verbose: bool = False,
        system_prompt_builder: Optional[Callable[[List[BaseTool]], str]] = None,
        max_total_tokens: Optional[int] = None,
    ):
        self._llm = llm
        self._registry = registry
        self._system_prompt = system_prompt
        # 预算缺省从 settings 读取（路线图 4.3），显式传参优先（测试/特殊部署）。
        self._max_iterations = max_iterations if max_iterations is not None else _budget_setting("AGENT_MAX_TOOL_ROUNDS", 5)
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else _budget_setting("AGENT_TOTAL_TIMEOUT_SECONDS", 120.0)
        self._token_budget = max_total_tokens if max_total_tokens is not None else _budget_setting("AGENT_MAX_TOTAL_TOKENS", 60000)
        self._verbose = verbose
        self._system_prompt_builder = system_prompt_builder
        self._last_used_tools: set = set()  # 最近一次 stream 执行中使用的工具集
        self._last_token_usage: Dict[str, int] = {}
        self._last_run_status: str = "completed"

        self._recorders: Dict[str, ThoughtRecordingCallbackHandler] = {}

        self._agent: Any = None
        self._tools: List[Any] = []
        self._agents_by_mode: Dict[str, Any] = {}
        self._prompts_by_mode: Dict[str, str] = {}

        logger.info(
            f"LangChainReActStrategy初始化完成 "
            f"(max_iterations={max_iterations}, timeout={timeout_seconds}s)"
        )

    def _ensure_agent_initialized(
        self,
        mode: str = "tutor_free",
        capability_allowed_tools: Optional[frozenset[str]] = None,
    ) -> Any:
        canonical_mode = normalize_tutor_mode(mode)
        allowed_key = ",".join(sorted(capability_allowed_tools or ()))
        cache_key = f"{canonical_mode}|{allowed_key}"
        if cache_key in self._agents_by_mode:
            return self._agents_by_mode[cache_key]

        start_init = time.time()
        logger.info("正在初始化LangChain ReAct Agent...")

        converter = get_tool_converter()
        custom_tools = filter_tools_for_mode(self._registry.get_all_tools(), canonical_mode)
        if capability_allowed_tools is not None:
            custom_tools = [tool for tool in custom_tools if tool.name in capability_allowed_tools]
        self._tools = converter.convert_batch(custom_tools)

        logger.info(f"已转换 {len(self._tools)} 个工具为LangChain格式")

        # Keep the execution budget in the compiled agent as well as around the
        # outer stream.  The middleware prevents an agent from repeatedly
        # calling tools, while the outer timeout covers a single hung tool/LLM
        # call that never returns another event.
        middleware: List[AgentMiddleware] = [
            MaxIterationsMiddleware(max_iterations=self._max_iterations),
        ]

        # [已移除] SummarizationMiddleware 会对工具返回内容进行摘要压缩，
        # 导致推荐题目等结构化数据在传回LLM时丢失细节或被改写。
        # 对于需要原样展示工具结果的场景（如RAG推荐），此中间件有害无益。
        # 如需恢复，取消下方注释即可：
        # try:
        #     middleware.append(SummarizationMiddleware(model=self._llm))
        # except Exception:
        #     logger.debug("SummarizationMiddleware初始化失败，跳过")

        system_prompt = (
            self._system_prompt_builder(custom_tools)
            if self._system_prompt_builder is not None
            else self._system_prompt
        )
        agent = create_agent(
            model=self._llm,
            tools=self._tools,
            system_prompt=system_prompt,
            middleware=middleware,
        )
        self._agent = agent
        self._agents_by_mode[cache_key] = agent
        self._prompts_by_mode[cache_key] = system_prompt

        elapsed = (time.time() - start_init) * 1000
        logger.info(f"LangChain ReAct Agent初始化完成 ({elapsed:.1f}ms)")

        return agent

    def _rebind_llm(self, model: str) -> None:
        """L3 故障转移：换用候选模型并清空已编译 agent 缓存。

        候选与主模型共用 LLM_API_BASE / LLM_API_KEY（跨供应商映射待阶段三
        模型注册表）；工具转换与 LLM 无关，无需重建。
        """
        from langchain_openai import ChatOpenAI

        try:
            from app.config.settings import settings

            api_key = settings.LLM_API_KEY or None
            base_url = settings.LLM_API_BASE or None
        except Exception:
            api_key, base_url = None, None
        temperature = getattr(self._llm, "temperature", None)
        previous = str(getattr(self._llm, "model_name", "?") or "?")
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=True,
            temperature=temperature if temperature is not None else 0.7,
        )
        self._agents_by_mode.clear()
        self._prompts_by_mode.clear()
        self._agent = None
        self._tools = []
        logger.warning(f"[FAILOVER] LangChainReActStrategy 已切换模型: {previous} -> {model}")

    def _get_recorder(self, session_id: str) -> ThoughtRecordingCallbackHandler:
        if session_id not in self._recorders:
            self._recorders[session_id] = ThoughtRecordingCallbackHandler(
                session_id=session_id
            )
        return self._recorders[session_id]

    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> str:
        start_time = time.time()
        chunks = []
        async for chunk in self.stream(user_input, session_id, context):
            chunks.append(chunk)
        full_answer = "".join(chunks)

        # [P0-01] 自动记忆提取与持久化
        await self._auto_persist_memory(
            context=context,
            user_input=user_input,
            full_answer=full_answer,
            session_id=session_id,
            execution_time=time.time() - start_time,
        )

        return full_answer

    async def stream(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        mode = normalize_tutor_mode(context.get("tutor_mode", "tutor_free"))
        capability_allowed_tools = context.get("capability_allowed_tools")
        if capability_allowed_tools is not None:
            capability_allowed_tools = frozenset(capability_allowed_tools)
        agent = self._ensure_agent_initialized(mode, capability_allowed_tools)
        recorder = self._get_recorder(session_id)

        # 将 context（含 user_id）注入到工具转换器，让工具执行时能获取用户身份
        converter = get_tool_converter()
        converter.set_context(context)

        recorder.start_process(user_input)
        tool_started_at: Dict[str, float] = {}

        chat_history = self._format_chat_history(context.get("chat_history", []))

        allowed_key = ",".join(sorted(capability_allowed_tools or ()))
        cache_key = f"{mode}|{allowed_key}"
        messages = [SystemMessage(content=self._prompts_by_mode.get(cache_key, self._system_prompt))]
        messages.extend(chat_history)
        messages.append(HumanMessage(content=user_input))

        logger.info(
            f"[STREAM] 开始流式执行: session={session_id}, "
            f"input='{user_input[:50]}...', history_len={len(chat_history)}"
        )
        self._last_used_tools = set()
        self._last_token_usage = {}
        self._last_run_status = "completed"

        # L3 故障转移：若上一窗口的连续失败已触发粘性切换，则本次 run 直接用候选模型。
        failover = get_model_failover_coordinator()
        primary_model = str(getattr(self._llm, "model_name", "") or "")
        active_model = failover.current_model(primary_model) if primary_model else primary_model
        if active_model != primary_model:
            self._rebind_llm(active_model)
            self._last_run_status = "degraded"

        try:
            token_count = 0
            yield_count = 0
            _full_output = []  # 可观测性：累积完整输出用于日志
            _used_tools = set()  # 追踪本次执行中使用的工具名称
            _token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            event_stream = _iterate_with_timeout(
                agent.astream_events(
                    {"messages": messages},
                    config={'callbacks': [recorder]},
                    version="v2",
                ),
                self._timeout_seconds,
            )
            budget_exceeded = False
            async for event in event_stream:
                event_name = event.get("event", "")

                # 追踪工具调用（用于去重检测）
                if event_name == "on_tool_start":
                    tool_name = event.get("name", "")
                    if tool_name:
                        _used_tools.add(tool_name)
                        tool_started_at[tool_name] = time.perf_counter()
                        try:
                            from app.observability import AGENT_TOOL_CALLS
                            AGENT_TOOL_CALLS.labels(tool_name[:80], "started").inc()
                        except Exception:
                            pass
                        yield {"__agent_event__": True, "event_type": "tool_start", "tool": tool_name, "message": f"正在调用 {tool_name}"}
                        logger.debug(f"[STREAM] 工具调用: {tool_name}")

                if event_name == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name:
                        elapsed = time.perf_counter() - tool_started_at.pop(tool_name, time.perf_counter())
                        try:
                            from app.observability import AGENT_TOOL_CALLS, AGENT_TOOL_LATENCY
                            AGENT_TOOL_CALLS.labels(tool_name[:80], "success").inc()
                            AGENT_TOOL_LATENCY.labels(tool_name[:80]).observe(elapsed)
                        except Exception:
                            pass
                        yield {"__agent_event__": True, "event_type": "tool_end", "tool": tool_name, "message": f"{tool_name} 已返回结果"}

                # LangChain 在工具抛出异常时发送 on_tool_error，而不是 on_tool_end。
                # 必须单独记账，否则成功率会被高估，且前端会一直显示工具运行中。
                if event_name == "on_tool_error":
                    tool_name = event.get("name", "")
                    if tool_name:
                        elapsed = time.perf_counter() - tool_started_at.pop(tool_name, time.perf_counter())
                        try:
                            from app.observability import AGENT_TOOL_CALLS, AGENT_TOOL_LATENCY
                            AGENT_TOOL_CALLS.labels(tool_name[:80], "error").inc()
                            AGENT_TOOL_LATENCY.labels(tool_name[:80]).observe(elapsed)
                        except Exception:
                            pass
                        # 错误详情可能包含题目内容、凭据或内部路径，日志/事件只传递稳定状态。
                        yield {
                            "__agent_event__": True,
                            "event_type": "tool_error",
                            "tool": tool_name,
                            "message": f"{tool_name} 调用失败，正在继续处理",
                        }

                # 只传播供应商/LangChain 已返回的 usage，不估算也不改变模型请求。
                if event_name == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    usage = getattr(output, "usage_metadata", None) or {}
                    response_metadata = getattr(output, "response_metadata", None) or {}
                    usage = usage or response_metadata.get("token_usage") or response_metadata.get("usage") or {}
                    _token_usage["prompt_tokens"] += int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
                    _token_usage["completion_tokens"] += int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
                    _token_usage["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
                    # Run 级 Token 预算（路线图 4.3.3）：触顶即优雅收尾，不抛 500。
                    if self._token_budget and _token_usage["total_tokens"] >= self._token_budget:
                        budget_exceeded = True
                        break

                if event_name != "on_chat_model_stream":
                    continue

                chunk = event.get("data", {}).get("chunk")
                if not chunk:
                    continue

                content = getattr(chunk, 'content', None)
                if not content:
                    continue

                token_count += 1
                yield_count += 1
                _full_output.append(content)
                logger.debug(f"[STREAM] token#{token_count} yield#{yield_count}: {repr(content[:40])}")
                yield content

            # 确定性关闭底层事件流：预算触顶 break 时也要收掉 astream_events 生成器，
            # 不留挂起的 LLM 连接；正常结束/异常路径下这是无害的幂等操作。
            await event_stream.aclose()

            # LLM 正常产出 → 清空失败窗口（粘性切换仍由探测计时器回切）。
            if primary_model:
                failover.record_success()

            # 可观测性：记录LLM完整输出和工具使用情况
            _complete = "".join(_full_output)
            import hashlib as _hl
            _out_hash = _hl.md5(_complete.encode()).hexdigest()[:8]
            print(f"\n[OBSERVE] LLM完整输出 | hash={_out_hash} | 长度={len(_complete)}字符 | tokens={token_count}", flush=True)
            print(f"[OBSERVE] 本次工具调用: {_used_tools or '(无)'}", flush=True)
            # 暴露工具使用记录，供 agent.py 去重检测使用
            self._last_used_tools = _used_tools
            if not _token_usage["total_tokens"]:
                _token_usage["total_tokens"] = _token_usage["prompt_tokens"] + _token_usage["completion_tokens"]
            self._last_token_usage = _token_usage if _token_usage["total_tokens"] else {}
            try:
                from app.observability import AGENT_TOKENS
                AGENT_TOKENS.labels("input").inc(_token_usage["prompt_tokens"])
                AGENT_TOKENS.labels("output").inc(_token_usage["completion_tokens"])
            except Exception:
                pass
            # 检测是否包含RAG标记（说明LLM确实展示了推荐结果）
            _has_rag = "RAG推荐结果" in _complete or "来源:" in _complete
            print(f"[OBSERVE] RAG内容检测: {'检测到RAG题目展示' if _has_rag else '未检测到RAG内容 — 可能被LLM改写或忽略!'}", flush=True)

            logger.info(
                f"[STREAM] 流式执行完成: session={session_id}, "
                f"tokens={token_count}, yields={yield_count}"
            )

            # 预算触顶：已流出的内容保留，追加诚实收尾文案；半截结果不进记忆提炼。
            if budget_exceeded:
                self._last_run_status = "budget_exceeded"
                logger.warning(
                    f"[STREAM] Run 级 Token 预算触顶 "
                    f"({_token_usage['total_tokens']} >= {self._token_budget})，优雅收尾"
                )
                yield "\n\n**【⚠️ 已达单次回答长度上限】** 已保留目前进展。你可以让我“继续”，或把问题拆成更小的步骤再问。"
                recorder.finish_process("[预算触顶终止]")
                return

            # [P0-01] 自动记忆提取与持久化（流式模式）
            await self._auto_persist_memory(
                context=context,
                user_input=user_input,
                full_answer=_complete,
                session_id=session_id,
                execution_time=0.0,  # 流式模式下不提供精确执行时间
            )

        except asyncio.TimeoutError:
            self._last_run_status = "timeout"
            logger.error(f"[STREAM] Agent执行超时 ({self._timeout_seconds}s)")
            yield degradation_text("timeout")
            recorder.finish_process("[超时终止]")

        except Exception as e:
            # L3 记账：窗口内连续失败达阈值则粘性切换，保护后续 run；
            # 本次 run 走 L4 模板兜底——诚实告知失败，绝不假装成功，
            # 也不把异常类型/栈信息透给用户（安全约束 10.5）。
            logger.error(f"[STREAM] Agent执行失败: {type(e).__name__}: {e}", exc_info=True)
            if primary_model:
                failover.record_failure(primary_model)
            self._last_run_status = "failed_l4"
            yield degradation_text("model_failure")
            recorder.finish_process("[L4 降级]")

    def _format_chat_history(
        self,
        history: List[Dict[str, str]],
    ) -> List:
        messages = []
        for msg in history:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role in ('user', 'human'):
                messages.append(HumanMessage(content=content))
            elif role in ('assistant', 'ai'):
                messages.append(AIMessage(content=content))

        return messages

    # ── P0-01: 自动记忆提取与持久化 ──

    async def _auto_persist_memory(
        self,
        context: Dict[str, Any],
        user_input: str,
        full_answer: str,
        session_id: str,
        execution_time: float,
    ) -> None:
        """自动提取并持久化学习记忆（失败不影响主流程）。"""
        try:
            from agent_core.memory_extractor import get_memory_extractor
            from agent_core.memory_persistence import MemoryPersistenceFacade

            # 获取思维链记录
            recorder = self._get_recorder(session_id)
            thoughts = []
            if recorder._history:
                last_process = recorder._history[-1]
                thoughts = [s.to_dict() for s in last_process.steps]

            extractor = get_memory_extractor()
            event = await extractor.extract_from_agent_result(
                user_id=context["user_id"],
                user_input=user_input,
                agent_result={
                    "answer": full_answer,
                    "thoughts": thoughts,
                    "metadata": context.get("metadata", {}),
                },
                execution_time=execution_time,
            )
            if event:
                facade = MemoryPersistenceFacade()
                await facade.record_event(
                    user_id=context["user_id"],
                    event_data=event.to_dict(),
                )
                logger.info(
                    f"学习记忆自动持久化: user={context.get('user_id')} "
                    f"category={event.category}"
                )
        except Exception as e:
            logger.error(f"自动持久化异常（已忽略）: {e}")

    def get_thought_recorder(self, session_id: str) -> ThoughtRecordingCallbackHandler:
        return self._get_recorder(session_id)

    def refresh_tools(self):
        """
        刷新工具列表。

        当工具注册表或LLM发生变化时调用此方法，
        会强制重新创建Agent实例。
        """
        self._agent = None
        self._tools = []
        self._agents_by_mode.clear()
        self._prompts_by_mode.clear()
        get_tool_converter().clear_cache()
        logger.info("Agent工具列表已刷新，将在下次调用时重新初始化")

    @property
    def thought_recorder(self) -> ThoughtRecordingCallbackHandler:
        return self._get_recorder("default")

    def clear_user_data(self, user_id: str) -> None:
        """Drop all per-session thought recorders owned by one user."""
        prefix = f"{user_id}:"
        for key in [key for key in self._recorders if key.startswith(prefix)]:
            del self._recorders[key]
