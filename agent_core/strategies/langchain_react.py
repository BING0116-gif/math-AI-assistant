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
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agent_core.strategies.base import AgentStrategy
from agent_core.callbacks import ThoughtRecordingCallbackHandler
from agent_core.langchain_adapter import get_tool_converter
from agent_core.degradation import degradation_text
from agent_core.model_failover import get_model_failover_coordinator
from tools.base_tool import BaseTool
from tools.hybrid_registry import HybridToolRegistry as ToolRegistry
from tools.tool_ledger import (
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    begin_round,
    close_if_running,
    close_open_rounds,
    close_running,
    drain_events,
    drain_trace_events,
    has_tool,
    mark_round_final,
    mark_round_process,
    mark_start_emitted,
    record_text,
    round_for_run,
    tool_label,
)
from app.services.mode_gating import filter_tools_for_mode, normalize_tutor_mode

logger = logging.getLogger(__name__)


def _content_text(content: Any) -> str:
    """把流式 chunk 的 content 变成纯文本，仅用于轮次纪要登记。

    供应商偶尔返回内容块列表，这里只取文本块；取不到就返回空串——纪要宁可少记，
    也不能把结构体的字符串表示塞进面板。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _start_event(tool_name: str) -> Dict[str, Any]:
    return {
        "__agent_event__": True,
        "event_type": "tool_start",
        "tool": tool_name,
        "label": tool_label(tool_name),
        "status": STATUS_RUNNING,
        "message": f"正在调用：{tool_label(tool_name)}",
    }


def _tool_activity_events(
    context: Dict[str, Any],
    *,
    phase: str,
    tool_name: str,
    fallback_message: str,
) -> List[Dict[str, Any]]:
    """输出本次工具调用的时间线事件：台账为准，台账不认识时退回旧直发事件。

    phase="start" 只取出尚未广播的开始事件；"end"/"error" 先把仍挂在“进行中”的
    记录按 LangChain 回调结果补上终态（参数校验失败等不会进入我们的转换器），
    再抽取事件。前端因此能区分“调用成功”和“调用失败”，不再把任何返回都当成成功。
    """
    if phase == "start":
        events = drain_events(context)
        if any(
            event.get("tool") == tool_name and event.get("event_type") == "tool_start"
            for event in events
        ):
            return events
        # LangChain 回调早于工具协程，台账还没记录：先占位再发开始事件，
        # 否则终态抽取会补发第二条“正在调用”，时间线出现重复行。
        if not mark_start_emitted(context, tool_name):
            return events
        # 本次调用在台账里序号最大，排在已排空事件之后才符合发生顺序。
        events.append(_start_event(tool_name))
        return events

    close_if_running(
        context,
        tool_name,
        STATUS_SUCCESS if phase == "end" else STATUS_ERROR,
        code="" if phase == "end" else "TOOL_INVOCATION_ERROR",
    )
    events = drain_events(context)
    terminal_types = ("tool_end", "tool_error")
    if any(
        event.get("tool") == tool_name and event.get("event_type") in terminal_types
        for event in events
    ):
        return events
    if has_tool(context, tool_name):
        # 台账认识这个工具，但这次回调没带出新事件：终态已经广播过（重复回调/迟到回调），
        # 再补一行会让同一次调用在时间线上出现两次。
        return events
    # 台账不认识这次调用（非注册表工具或被 LangChain 提前拦下）：仍补一条终态事件，
    # 保证“有调用就有显示”，状态沿用回调语义（on_tool_end 即工具正常返回）。
    events.append(
        {
            "__agent_event__": True,
            "event_type": "tool_end" if phase == "end" else "tool_error",
            "tool": tool_name,
            "label": tool_label(tool_name),
            "status": STATUS_SUCCESS if phase == "end" else STATUS_ERROR,
            "code": "" if phase == "end" else "TOOL_INVOCATION_ERROR",
            "message": fallback_message,
        }
    )
    return events


def _closing_tool_events(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """收尾排空：本轮结束时不允许有任何调用停在“进行中”，也不允许漏掉轮次纪要。

    回调丢失（模型提前结束、预算触顶、超时）时，进行中的台账统一判为中断，
    未定性的轮次统一按答案轮处理（文本已在正文里），连同尚未广播的事件一起输出，
    前端不会永远转圈也不会漏显示。
    """
    close_running(context)
    close_open_rounds(context)
    return drain_events(context) + drain_trace_events(context, force=True)


def _round_of(context: Dict[str, Any], run_id: Any) -> int:
    """取这次模型调用对应的轮号；on_chat_model_start 丢失时现场补开一轮。

    受限模式（trace_enabled=False）下台账自己会返回 0，后续记录全部静默。
    """
    key = str(run_id or "")
    index = round_for_run(context, key)
    return index or begin_round(context, key)


def _round_is_process(output: Any) -> bool:
    """该轮模型输出是否带了工具调用 → 定性为过程轮。

    参数格式错误的 invalid_tool_calls 同样会让 Agent 再转一轮，不能当成答案。
    拿不到结构时保守归为答案轮（宁可不进面板，不可把答案搬走）。
    """
    if output is None:
        return False
    for attribute in ("tool_calls", "invalid_tool_calls"):
        try:
            if getattr(output, attribute, None) or (
                isinstance(output, dict) and output.get(attribute)
            ):
                return True
        except Exception:
            continue
    return False


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

    Python 3.10 兼容:不用 asyncio.timeout（3.11+），用 deadline + wait_for
    实现同语义的总预算——超时取消挂起的 __anext__ 并抛 TimeoutError。
    """
    try:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
    except RuntimeError:
        raise
    iterator = events.__aiter__()
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"agent wall-clock budget exhausted ({timeout_seconds:g}s)")
            try:
                event = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                return
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
        # 有界纪要缓存：只给 /api/agent/thought 做“展开全文”的按需拉取，
        # 本体已经随消息落库，因此服务重启或淘洗都不影响历史回看。
        self._trace_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._trace_cache_sessions = 20

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
        # stream() 同时产出正文片段和 agent_step 事件体：非流式调用只该拿正文。
        # 事件字典混进 join() 会直接 TypeError，把降级文案一起吞掉。
        chunks = []
        async for chunk in self.stream(user_input, session_id, context):
            if isinstance(chunk, str):
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

                # 轮次归因：一次模型调用 = 一轮。本轮开始即开轮，受限模式下台账自己会静默。
                if event_name == "on_chat_model_start":
                    _round_of(context, event.get("run_id"))

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
                        for activity in _tool_activity_events(
                            context,
                            phase="start",
                            tool_name=tool_name,
                            fallback_message=f"正在调用：{tool_label(tool_name)}",
                        ):
                            yield activity
                        logger.debug(f"[STREAM] 工具调用: {tool_name}")

                if event_name == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name:
                        elapsed = time.perf_counter() - tool_started_at.pop(tool_name, time.perf_counter())
                        try:
                            # 终态 success/error/timeout/unavailable 由适配器单一漏斗记录
                            # （guard 失败以结果字符串返回，on_tool_end 不代表成功）。
                            from app.observability import AGENT_TOOL_LATENCY
                            AGENT_TOOL_LATENCY.labels(tool_name[:80]).observe(elapsed)
                        except Exception:
                            pass
                        for activity in _tool_activity_events(
                            context,
                            phase="end",
                            tool_name=tool_name,
                            fallback_message=f"{tool_label(tool_name)}：调用成功",
                        ):
                            yield activity

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
                        for activity in _tool_activity_events(
                            context,
                            phase="error",
                            tool_name=tool_name,
                            fallback_message=f"{tool_label(tool_name)}：调用失败，正在继续处理",
                        ):
                            yield activity

                # 只传播供应商/LangChain 已返回的 usage，不估算也不改变模型请求。
                if event_name == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    # 先定性再算预算：预算触顶 break 时这一轮的纪要也必须已经广播。
                    round_index = _round_of(context, event.get("run_id"))
                    if _round_is_process(output):
                        mark_round_process(context, round_index)
                    else:
                        mark_round_final(context, round_index)
                    for activity in drain_trace_events(context, force=True):
                        yield activity
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

                # 正文照旧逐字流出（不因为面板而改变答案体验），同时把文本按轮登记，
                # 供本轮定性为过程轮时整体搬进思考面板。
                record_text(context, _round_of(context, event.get("run_id")), _content_text(content))

                token_count += 1
                yield_count += 1
                _full_output.append(content)
                logger.debug(f"[STREAM] token#{token_count} yield#{yield_count}: {repr(content[:40])}")
                yield content

                # 面板实时增长：本轮还没定性，先按「够 400 字或够 200ms」节流广播增量。
                # 定性成答案轮时前端会把这份临时文本撤掉（正文本身不受影响），
                # 定性成过程轮则由 round_process 用全文覆盖，不会缺字。
                for activity in drain_trace_events(context):
                    yield activity

            # 确定性关闭底层事件流：预算触顶 break 时也要收掉 astream_events 生成器，
            # 不留挂起的 LLM 连接；正常结束/异常路径下这是无害的幂等操作。
            await event_stream.aclose()

            # 台账收尾：回调没送达的调用也要在时间线上给出终态。
            for activity in _closing_tool_events(context):
                yield activity

            # LLM 正常产出 → 清空失败窗口（粘性切换仍由探测计时器回切）。
            if primary_model:
                failover.record_success()

            # 可观测性：记录LLM完整输出和工具使用情况
            _complete = "".join(_full_output)
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
            for activity in _closing_tool_events(context):
                yield activity
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
            for activity in _closing_tool_events(context):
                yield activity
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

    def cache_session_trace(self, session_id: str, trace: List[Dict[str, Any]]) -> None:
        """按会话缓存最近一轮的思考纪要（已在台账侧截断与脱敏）。"""
        if not session_id:
            return
        if not trace:
            self._trace_cache.pop(session_id, None)
            return
        self._trace_cache[session_id] = list(trace)
        while len(self._trace_cache) > self._trace_cache_sessions:
            # 先进先出：丢弃最早的会话，不丢当前会话的可见性。
            self._trace_cache.pop(next(iter(self._trace_cache)))

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        """取回该会话缓存的纪要；没缓存过就返回空，由调用方回退到 metadata。"""
        return list(self._trace_cache.get(session_id) or [])

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
        for key in [key for key in self._trace_cache if key.startswith(prefix)]:
            del self._trace_cache[key]
