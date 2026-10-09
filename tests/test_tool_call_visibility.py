"""统一工具调用可见性回归。

覆盖三层契约：
1. tools/tool_ledger：台账记录真实终态，并按顺序抽取时间线事件；
2. 执行入口（注册表直连 + LangChain 转换器）：任何封装工具调用都会写台账；
3. 策略层：时间线事件反映工具真实结果，而不是把 on_tool_end 一律当作成功。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from tools.base_tool import BaseTool, ToolCapability, ToolInput, ToolOutput
from tools.hybrid_registry import HybridToolRegistry
from tools.tool_ledger import (
    LEDGER_KEY,
    MAX_ROUND_TEXT_CHARS,
    MAX_TRACE_ROUNDS,
    MAX_TRACE_TOTAL_CHARS,
    REASONING_BATCH_CHARS,
    REASONING_BATCH_MS,
    STATUS_ABORTED,
    STATUS_DENIED,
    STATUS_ERROR,
    STATUS_SUCCESS,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
    TRACE_ENABLED_KEY,
    TRACE_KEY,
    begin_call,
    begin_round,
    close_if_running,
    close_running,
    current_round,
    drain_events,
    drain_trace_events,
    ensure_ledger,
    finish_call,
    mark_round_final,
    mark_round_process,
    mark_start_emitted,
    public_summary,
    public_trace,
    record_text,
    record_tool_io,
    round_for_run,
    summarize_parameters,
    summarize_result,
    tool_label,
    strip_process_text,
)


class _EchoTool(BaseTool):
    name = "math_visualize"
    description = "返回成功的测试工具"
    capabilities = [ToolCapability.PLOTTING]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        return ToolOutput(success=True, result="已生成图像数据", tool_name=self.name)


class _BrokenTool(BaseTool):
    name = "math_verify"
    description = "返回失败结果的测试工具"
    capabilities = [ToolCapability.VERIFICATION]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        return ToolOutput(success=False, error="符号计算库不可用", tool_name=self.name)


class _DeniedTool(BaseTool):
    name = "explain_question"
    description = "受限模式下应被拒绝的工具"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        return ToolOutput(success=True, result="答案泄露", tool_name=self.name)


def _events_by_type(events):
    return [event["event_type"] for event in events]


def _terminal_event(events):
    terminals = [e for e in events if e["event_type"] in ("tool_end", "tool_error")]
    assert terminals, f"缺少终态事件: {events}"
    return terminals[-1]


@pytest.fixture(autouse=True)
def _frozen_trace_clock(monkeypatch):
    """纪要的时间闸门走可注入时钟：默认钉在同一个时刻，
    事件序列的断言才不会因为真实耗时偶发跨过 200ms 而多出一条 reasoning。"""
    import tools.tool_ledger as tool_ledger_module

    monkeypatch.setattr(tool_ledger_module, "_clock", lambda: 0.0)


# ---------------------------------------------------------------------------
# 台账本体
# ---------------------------------------------------------------------------


def test_ledger_emits_start_then_success_event():
    context = {}
    begin_call(context, "math_visualize")
    finish_call(context, "math_visualize", STATUS_SUCCESS, elapsed_ms=12.5)

    events = drain_events(context)
    assert _events_by_type(events) == ["tool_start", "tool_end"]
    assert events[0]["label"] == "函数图像绘制"
    assert _terminal_event(events)["status"] == STATUS_SUCCESS
    assert _terminal_event(events)["elapsed_ms"] == 12.5
    # 事件只发一次
    assert drain_events(context) == []


@pytest.mark.parametrize(
    "status,expected_type",
    [
        (STATUS_ERROR, "tool_error"),
        (STATUS_TIMEOUT, "tool_error"),
        (STATUS_UNAVAILABLE, "tool_error"),
        (STATUS_DENIED, "tool_error"),
        (STATUS_ABORTED, "tool_error"),
    ],
)
def test_ledger_maps_every_unsuccessful_status_to_tool_error(status, expected_type):
    context = {}
    begin_call(context, "math_verify")
    finish_call(context, "math_verify", status, code="TOOL_TIMEOUT")

    terminal = _terminal_event(drain_events(context))
    assert terminal["event_type"] == expected_type
    assert terminal["status"] == status
    assert terminal["code"] == "TOOL_TIMEOUT"


def test_mark_start_emitted_avoids_duplicate_start_line():
    """LangChain 回调早于工具协程：占位后台账不能再补发一次“正在调用”。"""
    context = {}
    mark_start_emitted(context, "search_questions")
    begin_call(context, "search_questions", source="langchain_agent")
    finish_call(context, "search_questions", STATUS_SUCCESS)

    events = drain_events(context)
    assert _events_by_type(events) == ["tool_end"]
    assert len(context[LEDGER_KEY]) == 1


def test_close_running_marks_orphan_calls_aborted():
    context = {}
    begin_call(context, "math_visualize")
    close_running(context)

    terminal = _terminal_event(drain_events(context))
    assert terminal["status"] == STATUS_ABORTED
    assert "已中断" in terminal["message"]


def test_close_if_running_keeps_recorded_terminal_status():
    """真实终态优先：回调后到不能把 guard 判定的超时改写成成功。"""
    context = {}
    begin_call(context, "math_verify")
    finish_call(context, "math_verify", STATUS_TIMEOUT, code="TOOL_TIMEOUT")

    assert close_if_running(context, "math_verify", STATUS_SUCCESS) is False
    entry = public_summary(context)[0]
    assert entry["status"] == STATUS_TIMEOUT


def test_public_summary_is_safe_low_cardinality_trace():
    context = {}
    begin_call(context, "math_visualize")
    finish_call(context, "math_visualize", STATUS_SUCCESS)

    summary = public_summary(context)
    assert len(summary) == 1
    assert summary[0]["tool"] == "math_visualize"
    assert summary[0]["label"] == "函数图像绘制"
    assert summary[0]["status"] == STATUS_SUCCESS
    assert summary[0]["code"] == ""
    assert set(summary[0]) == {"tool", "label", "status", "code", "elapsed_ms"}
    assert tool_label("brand_new_tool") == "brand_new_tool"


def test_ledger_ignores_non_dict_context():
    begin_call(None, "math_visualize")
    finish_call(None, "math_visualize", STATUS_SUCCESS)
    assert drain_events(None) == []
    assert public_summary(None) == []


# ---------------------------------------------------------------------------
# 注册表直连入口（多模态识图等）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_direct_call_is_recorded_in_ledger():
    registry = HybridToolRegistry()
    registry.register(_EchoTool())
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}
    ensure_ledger(context)

    result = await registry.execute_safe("math_visualize", ToolInput(query="画 y=x", context=context))

    assert result.success is True
    terminal = _terminal_event(drain_events(context))
    assert terminal["event_type"] == "tool_end"
    assert terminal["status"] == STATUS_SUCCESS


def test_ledger_survives_toolinput_context_copy():
    """Pydantic 会复制 context 字典：预置的台账列表仍是同一个对象，记录才不会丢。"""
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}
    ensure_ledger(context)

    input_data = ToolInput(query="x", context=context)
    input_data.context[LEDGER_KEY].append({"probe": True})

    assert context[LEDGER_KEY] == [{"probe": True}]


@pytest.mark.asyncio
async def test_registry_records_unsuccessful_tool_output_as_error():
    registry = HybridToolRegistry()
    registry.register(_BrokenTool())
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}
    ensure_ledger(context)

    result = await registry.execute_safe("math_verify", ToolInput(query="验证", context=context))

    assert result.success is False
    terminal = _terminal_event(drain_events(context))
    assert terminal["event_type"] == "tool_error"
    assert terminal["status"] == STATUS_ERROR


@pytest.mark.asyncio
async def test_registry_records_mode_denied_call():
    registry = HybridToolRegistry()
    registry.register(_DeniedTool())
    context = {"tutor_mode": "hint_only", "user_id": "user-a", "mode_tool_denials": []}
    ensure_ledger(context)

    result = await registry.execute_safe(
        "explain_question", ToolInput(query="直接给答案", context=context)
    )

    assert result.success is False
    terminal = _terminal_event(drain_events(context))
    assert terminal["status"] == STATUS_DENIED
    assert terminal["code"] == "MODE_TOOL_DENIED"


@pytest.mark.asyncio
async def test_registry_records_missing_tool_call():
    registry = HybridToolRegistry()
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}
    ensure_ledger(context)

    result = await registry.execute_safe("ghost_tool", ToolInput(query="x", context=context))

    assert result.success is False
    terminal = _terminal_event(drain_events(context))
    assert terminal["code"] == "TOOL_NOT_FOUND"


# ---------------------------------------------------------------------------
# LangChain 转换器（Agent 主路径）
# ---------------------------------------------------------------------------


async def _invoke_converted(tool, context):
    from agent_core.langchain_adapter import LangChainToolConverter

    converter = LangChainToolConverter()
    converter.set_context(context)
    lc_tool = converter.convert(tool)
    return await lc_tool.coroutine(query="执行一次")


@pytest.mark.asyncio
async def test_converter_success_writes_real_terminal_status():
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}

    await _invoke_converted(_EchoTool(), context)

    events = drain_events(context)
    assert _events_by_type(events) == ["tool_start", "tool_end"]
    assert events[-1]["status"] == STATUS_SUCCESS


@pytest.mark.asyncio
async def test_converter_failure_is_not_reported_as_success():
    """工具返回 success=False 时，台账必须给出失败终态，供时间线显示“调用失败”。"""
    context = {"tutor_mode": "tutor_free", "user_id": "user-a"}

    output = await _invoke_converted(_BrokenTool(), context)

    assert "[错误]" in output
    terminal = _terminal_event(drain_events(context))
    assert terminal["event_type"] == "tool_error"
    assert terminal["status"] == STATUS_ERROR


@pytest.mark.asyncio
async def test_converter_denied_call_is_visible_in_ledger():
    context = {"tutor_mode": "hint_only", "user_id": "user-a"}

    await _invoke_converted(_DeniedTool(), context)

    terminal = _terminal_event(drain_events(context))
    assert terminal["status"] == STATUS_DENIED


# ---------------------------------------------------------------------------
# 策略层事件抽取
# ---------------------------------------------------------------------------


def _strategy_helpers():
    from agent_core.strategies import langchain_react as module

    return module._tool_activity_events, module._closing_tool_events


def test_strategy_start_phase_registers_pending_call_once():
    activity_events, closing = _strategy_helpers()
    context = {}

    first = activity_events(
        context, phase="start", tool_name="math_visualize", fallback_message="正在调用：函数图像绘制"
    )
    second = activity_events(
        context, phase="start", tool_name="math_visualize", fallback_message="正在调用：函数图像绘制"
    )

    assert _events_by_type(first) == ["tool_start"]
    assert second == []
    finish_call(context, "math_visualize", STATUS_SUCCESS)
    assert _events_by_type(closing(context)) == ["tool_end"]


def test_strategy_reports_tool_error_even_when_callback_says_end():
    """guard 已把这次调用判为超时：on_tool_end 不能把它洗成成功。"""
    activity_events, _ = _strategy_helpers()
    context = {}
    begin_call(context, "math_verify")
    finish_call(context, "math_verify", STATUS_TIMEOUT, code="TOOL_TIMEOUT")

    events = activity_events(
        context, phase="end", tool_name="math_verify", fallback_message="数学验证：调用成功"
    )

    terminal = _terminal_event(events)
    assert terminal["event_type"] == "tool_error"
    assert terminal["status"] == STATUS_TIMEOUT


def test_strategy_marks_ledger_success_when_adapter_wrote_nothing():
    activity_events, _ = _strategy_helpers()
    context = {}
    begin_call(context, "math_visualize")

    events = activity_events(
        context, phase="end", tool_name="math_visualize", fallback_message="函数图像绘制：调用成功"
    )

    terminal = _terminal_event(events)
    assert terminal["event_type"] == "tool_end"
    assert terminal["status"] == STATUS_SUCCESS


def test_strategy_falls_back_for_tool_unknown_to_ledger():
    """非注册表工具（无台账记录）也要留下一行调用记录，不能静默吞掉。"""
    activity_events, _ = _strategy_helpers()
    context = {}

    events = activity_events(
        context, phase="end", tool_name="external_tool", fallback_message="external_tool：调用成功"
    )

    assert _events_by_type(events) == ["tool_end"]
    assert events[0]["tool"] == "external_tool"


def test_strategy_closing_events_abort_running_calls():
    _, closing = _strategy_helpers()
    context = {}
    begin_call(context, "math_visualize")

    events = closing(context)

    # 没人写终态的调用不能假装成功：补发开始 + 中断两个事件。
    assert _events_by_type(events) == ["tool_start", "tool_error"]
    assert events[1]["status"] == STATUS_ABORTED


# ---------------------------------------------------------------------------
# 策略 stream 端到端：LangChain 事件流 → agent_step 时间线
# ---------------------------------------------------------------------------


def _build_strategy(monkeypatch, events_callable):
    from agent_core.strategies import langchain_react as strategy_module

    strategy = strategy_module.LangChainReActStrategy(
        llm=object(),
        registry=SimpleNamespace(get_all_tools=lambda: []),
        system_prompt="test",
        timeout_seconds=5,
    )

    async def _noop_persist(**kwargs):
        return None

    monkeypatch.setattr(strategy, "_auto_persist_memory", _noop_persist)
    monkeypatch.setattr(
        strategy,
        "_ensure_agent_initialized",
        lambda mode, capability_allowed_tools: SimpleNamespace(
            astream_events=events_callable
        ),
    )
    return strategy


def _run_strategy_stream(monkeypatch, events_callable, context):
    async def scenario():
        strategy = _build_strategy(monkeypatch, events_callable)
        return [
            chunk
            async for chunk in strategy.stream(
                "画出 y=x^2", "session-visibility", context
            )
        ]

    return asyncio.run(scenario())


def _run_strategy_execute(monkeypatch, events_callable, context):
    """非流式入口 /solve 一类走 execute()：返回值必须是纯正文。"""

    async def scenario():
        strategy = _build_strategy(monkeypatch, events_callable)
        return await strategy.execute("画出 y=x^2", "session-visibility", context)

    return asyncio.run(scenario())


def _new_context():
    return {"user_id": "user-visibility", "tutor_mode": "tutor_free"}


def test_strategy_stream_reports_tool_timeout_even_if_callback_says_end(monkeypatch):
    """真实场景：guard 判为超时后工具依旧“正常返回”字符串，on_tool_end 不能洗白成成功。"""
    context = _new_context()

    async def tool_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "math_visualize", "data": {}}
        # 适配器（真正的执行体）往同一个台账写入真实终态
        begin_call(context, "math_visualize", source="langchain_agent")
        finish_call(context, "math_visualize", STATUS_TIMEOUT, code="TOOL_TIMEOUT")
        yield {"event": "on_tool_end", "name": "math_visualize", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="图像暂时画不出来")},
        }

    chunks = _run_strategy_stream(monkeypatch, tool_events, context)

    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]
    assert _events_by_type(steps) == ["tool_start", "tool_error"]
    assert steps[0]["label"] == "函数图像绘制"
    assert steps[-1]["status"] == STATUS_TIMEOUT
    assert steps[-1]["code"] == "TOOL_TIMEOUT"
    assert any(isinstance(chunk, str) for chunk in chunks)


def test_strategy_stream_reports_success_terminal_from_ledger(monkeypatch):
    context = _new_context()

    async def tool_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "math_visualize", "data": {}}
        begin_call(context, "math_visualize", source="langchain_agent")
        finish_call(context, "math_visualize", STATUS_SUCCESS, elapsed_ms=320.5)
        yield {"event": "on_tool_end", "name": "math_visualize", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="图像已生成")},
        }

    chunks = _run_strategy_stream(monkeypatch, tool_events, context)

    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]
    assert _events_by_type(steps) == ["tool_start", "tool_end"]
    assert steps[-1]["status"] == STATUS_SUCCESS
    assert steps[-1]["elapsed_ms"] == 320.5
    # 落库用的执行轨迹与时间线同源，不会漏掉这次成功调用
    assert public_summary(context)[0]["status"] == STATUS_SUCCESS


def test_strategy_stream_closes_tool_left_running_when_callback_never_arrives(monkeypatch):
    context = _new_context()

    async def dangling_tool_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "math_verify", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="直接给结论")},
        }

    chunks = _run_strategy_stream(monkeypatch, dangling_tool_events, context)

    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]
    assert _events_by_type(steps) == ["tool_start", "tool_error"]
    assert steps[-1]["status"] == STATUS_ABORTED
    assert public_summary(context)[-1]["status"] == STATUS_ABORTED


# ---------------------------------------------------------------------------
# 思考过程纪要：轮次归因、摘要脱敏与预算
# ---------------------------------------------------------------------------


def _trace_context(mode: str = "tutor_free"):
    """复刻 agent._build_context 的成果：台账预挂 + 按模式定采集开关。"""
    context = {
        "user_id": "user-visibility",
        "tutor_mode": mode,
        TRACE_ENABLED_KEY: mode == "tutor_free",
    }
    ensure_ledger(context)
    return context


def _trace_types(events):
    return _events_by_type([e for e in events if e["event_type"] in ("reasoning", "round_process", "round_final", "tool_io")])


def test_trace_rounds_separate_process_text_from_final_answer():
    context = _trace_context()
    first = begin_round(context, "run-1")
    assert begin_round(context, "run-1") == first  # 同一 run_id 幂等
    assert (first, current_round(context), round_for_run(context, "run-1")) == (1, 1, 1)

    narration = "我先取几个点，再调用绘图工具。"
    record_text(context, first, narration)
    begin_call(context, "math_visualize", source="langchain_agent")
    record_tool_io(
        context,
        "math_visualize",
        input_summary="type=function_plot, points=3",
        output_summary="status=ok",
    )
    finish_call(context, "math_visualize", STATUS_SUCCESS, elapsed_ms=210.5)
    mark_round_process(context, first)

    second = begin_round(context, "run-2")
    record_text(context, second, "图像已生成，开口向上。")
    mark_round_final(context, second)

    events = drain_trace_events(context, force=True)
    assert _events_by_type(events) == ["round_process", "tool_io", "round_final"]
    # 前端靠这段全文把正文尾部的过程解说原样搬进面板
    assert events[0]["round"] == 1 and events[0]["text"] == narration
    assert events[1]["tool"] == "math_visualize" and events[1]["round"] == 1
    assert events[1]["input_summary"] == "type=function_plot, points=3"
    assert events[1]["output_summary"] == "status=ok"
    assert events[2]["round"] == 2 and "text" not in events[2]
    assert drain_trace_events(context, force=True) == []  # 同一纪要不重播

    trace = public_trace(context)
    assert [item["round"] for item in trace] == [1, 2]
    assert trace[0]["kind"] == "process" and trace[0]["text"] == narration
    assert trace[0]["tools"][0]["status"] == STATUS_SUCCESS
    assert trace[0]["tools"][0]["input_summary"] == "type=function_plot, points=3"
    # 答案轮文本已经在正文里落库，纪要不再存一遍
    assert trace[1]["kind"] == "final" and trace[1]["text"] == ""


def test_trace_reasoning_waits_for_batch_budget_and_never_duplicates():
    context = _trace_context()
    round_index = begin_round(context, "run-1")
    record_text(context, round_index, "先" * (REASONING_BATCH_CHARS - 1))
    assert drain_trace_events(context) == []

    record_text(context, round_index, "先")
    events = drain_trace_events(context)
    assert _events_by_type(events) == ["reasoning"]
    assert len(events[0]["text"]) == REASONING_BATCH_CHARS

    # 定性为过程轮后全文由 round_process 携带，同一批文本不能再来一遍
    record_text(context, round_index, "补充一句")
    mark_round_process(context, round_index)
    follow_up = drain_trace_events(context, force=True)
    assert _events_by_type(follow_up) == ["round_process"]
    assert follow_up[0]["text"].endswith("补充一句")
    assert len(follow_up[0]["text"]) == REASONING_BATCH_CHARS + 4


def test_round_text_and_total_budgets_stay_bounded():
    context = _trace_context()
    round_index = begin_round(context, "run-1")
    record_text(context, round_index, "字" * (MAX_ROUND_TEXT_CHARS + 500))
    mark_round_process(context, round_index)
    events = drain_trace_events(context, force=True)
    assert len(events[0]["text"]) == MAX_ROUND_TEXT_CHARS
    assert events[0]["truncated"] is True

    bounded = _trace_context()
    for index in range(MAX_TRACE_ROUNDS):
        current = begin_round(bounded, f"run-{index}")
        record_text(bounded, current, "y" * MAX_ROUND_TEXT_CHARS)
        mark_round_process(bounded, current)
    trace = public_trace(bounded)
    assert sum(len(item["text"]) for item in trace) <= MAX_TRACE_TOTAL_CHARS
    assert trace[-1]["truncated"] is True
    assert trace[0]["truncated"] is False


def test_public_trace_keeps_first_and_last_rounds_when_too_many():
    context = _trace_context()
    for index in range(MAX_TRACE_ROUNDS + 3):
        current = begin_round(context, f"run-{index}")
        record_text(context, current, "z" * 20)
        mark_round_process(context, current)

    trace = public_trace(context)
    assert trace[0]["kind"] == "omitted"
    assert [item["round"] for item in trace if item["kind"] != "omitted"] == [1, 2, 3, 4, 5, 9, 10, 11]


def test_trace_events_stay_inside_sse_replay_budget():
    """长思考的重放预算（P0-3 口径）：定性后的轮只发一条 round_process，
    事件条数与字节数都要留在 sse_replay 缓冲上限内，否则断线重放会撑坏整条流。"""
    from app.config.settings import settings

    context = _trace_context()
    for index in range(MAX_TRACE_ROUNDS * 2):
        current = begin_round(context, f"run-{index}")
        record_text(context, current, "长" * MAX_ROUND_TEXT_CHARS)
        mark_round_process(context, current)

    events = drain_trace_events(context, force=True)
    payload = "".join(json.dumps(item, ensure_ascii=False) for item in events)

    assert len(events) < settings.SSE_BUFFER_MAX_EVENTS
    assert len(payload.encode("utf-8")) < settings.SSE_BUFFER_MAX_BYTES
    assert sum(len(item["text"]) for item in public_trace(context)) <= MAX_TRACE_TOTAL_CHARS


def test_trace_collection_is_off_until_a_caller_proves_the_mode():
    """没设 trace_enabled 的入口一律不采（fail-closed），但工具时间线照旧完整。"""
    context = {"user_id": "user-visibility", "tutor_mode": "hint_only"}
    ensure_ledger(context)
    assert begin_round(context, "run-1") == 0
    assert current_round(context) == 0
    record_text(context, 0, "过程解说")
    mark_round_process(context, 0)
    record_tool_io(context, "math_verify", input_summary="type=derivative")

    assert drain_trace_events(context, force=True) == []
    assert public_trace(context) == []
    begin_call(context, "math_verify")
    finish_call(context, "math_verify", STATUS_SUCCESS)
    assert _events_by_type(drain_events(context)) == ["tool_start", "tool_end"]


def test_parameter_summary_keeps_structure_and_drops_question_text():
    summary = summarize_parameters(
        {
            "query": "已知函数 f(x)=x^2，求 x>0 时的最小值",
            "type": "function_plot",
            "spec": {"points": [[0, 0], [1, 1], [2, 4]], "title": "已知函数 f(x)=x^2 的图像"},
        }
    )
    assert summary == "type=function_plot, points=3"
    assert "最小值" not in summary and "已知" not in summary and "title" not in summary
    # 本地路径一类参数不进摘要：只报带了哪些键名，不携任何值
    assert summarize_parameters({"image_source": "C:\\Users\\huawei\\uploads\\secret.png"}) == "params=image_source"
    assert summarize_parameters({"query": "已知函数 f(x)=x^2，求最小值"}) == "params=query"
    assert summarize_parameters([{"id": 1}, {"id": 2}]) == "count=2"
    assert "x^2" not in summarize_parameters({"query": "已知函数 f(x)=x^2，求最小值"})


def test_parameter_summary_unpacks_json_string_arguments():
    """模型会把子参数当成 JSON 或 Python 字面量字符串交过来，拆开才能抽白名单字段。"""
    assert (
        summarize_parameters({"parameters": '{"query": "求 f(x)=x^2 的最小值", "type": "function_plot"}'})
        == "type=function_plot"
    )
    assert (
        summarize_parameters({"parameters": "{'query': '求最小值', 'type': 'function_plot'}"})
        == "type=function_plot"
    )
    assert summarize_parameters({"parameters": '{"query": "求最小值"}'}) == "params=query"
    # 拆不开、或只看得到「parameters」这种包裹层名字时宁可不报，不把空壳词丢进面板
    assert summarize_parameters({"parameters": "{not json"}) == ""
    assert summarize_parameters({"parameters": "画抛物线 y=x^2"}) == ""
    assert summarize_parameters({"parameters": {}}) == ""
    assert summarize_parameters({"spec": '{"series": [{"points": [[0, 1], [1, 2]]}]}'}) == "series=1, points=2"


def test_parameter_summary_prefers_scalar_keys_over_structures():
    """入参名列表只报标量字段，不把 payload 这类容器名当噪声丢进面板。"""
    assert summarize_parameters({"query": "题干原文", "payload": {"a": 1}, "draft": ["x"]}) == "params=query"
    # 入参里没填的列表不报数量；结果里的空命中数量仍然要报（见 _status_facts）
    assert summarize_parameters({"type": "function_plot", "annotations": [], "series": [{"points": [[0, 1]]}]}) == \
        "type=function_plot, series=1"
    assert summarize_result({"data": {"items": []}}) == "items=0"


def test_parameter_summary_unpacks_multi_kilobyte_plot_specs():
    """绘图 spec 字符串动辄几 KB（上百个采样点），上限太小就只能报空。"""
    spec = json.dumps({"type": "function_plot", "points": [[i, i * i] for i in range(300)]})
    assert 2000 < len(spec) < 8000
    assert summarize_parameters({"parameters": spec}) == "type=function_plot, points=300"
    # 真顶到字面量上限就不拆了：宁可不报也不去解析任意长文本
    huge = json.dumps({"type": "function_plot", "points": [[i, i * i] for i in range(600)]})
    assert summarize_parameters({"parameters": huge}) == ""
    assert summarize_parameters({"query": "x" * 40000}) == "params=query"


def test_parameter_summary_unpacks_pydantic_arguments_from_langchain():
    """LangChain 按 args_schema 校验后交给工具的是模型实例，不是 dict。

    绘图入参整行摘要为空就是这么来的：拆不开嵌套模型，只剩一个
    被规则吐掉的 parameters 包裹层名字。这里按适配器实际送出的 kwargs 形状验证。
    """
    from tools.math_visualize_tool import MathVisualizeArgs

    args = MathVisualizeArgs.model_validate(
        {
            "query": "画出开口向上的抛物线",
            "parameters": {
                "type": "function_plot",
                "spec": {
                    "type": "function_plot",
                    "title": "y=x^2 的图像",
                    "viewport": {"x_min": -2, "x_max": 2, "y_min": -1, "y_max": 4},
                    "series": [{"kind": "curve", "points": [[-2, 4], [0, 0], [2, 4]]}],
                },
            },
        }
    )
    summary = summarize_parameters({"parameters": args.parameters})
    assert summary == "type=function_plot, series=1, points=3"
    assert "画出" not in summary and "title" not in summary and "y=x^2" not in summary

    tangent = MathVisualizeArgs.model_validate({"query": "切线", "parameters": {"type": "tangent_line"}})
    assert summarize_parameters({"parameters": tangent.parameters}) == "type=tangent_line"


def test_failed_tool_without_summary_still_reaches_the_panel():
    """被 LangChain 提前拦下的调用组不出摘要，但失败终态本身就是要给学生的信息。"""
    context = _trace_context()
    current = begin_round(context, "run-1")
    record_text(context, current, "先试一次。")
    mark_round_process(context, current)
    begin_call(context, "math_visualize", source="langchain_agent")
    finish_call(context, "math_visualize", STATUS_ERROR, code="TOOL_INVOCATION_ERROR")

    events = drain_trace_events(context, force=True)
    io_events = [item for item in events if item["event_type"] == "tool_io"]
    assert len(io_events) == 1
    assert io_events[0]["status"] == STATUS_ERROR
    assert io_events[0]["code"] == "TOOL_INVOCATION_ERROR"
    # 流式与落库同口径：刷新后不会凭空多出一行
    assert [tool["status"] for row in public_trace(context) for tool in row["tools"]] == [STATUS_ERROR]


def test_successful_tool_without_summary_stays_out_of_the_panel():
    """什么结构事实都没报出来的成功调用不单独占一行，时间线已经有它了。"""
    context = _trace_context()
    current = begin_round(context, "run-1")
    record_text(context, current, "先试一次。")
    mark_round_process(context, current)
    begin_call(context, "math_visualize", source="langchain_agent")
    finish_call(context, "math_visualize", STATUS_SUCCESS)

    events = drain_trace_events(context, force=True)
    assert [item["event_type"] for item in events] == ["round_process"]
    assert [row["tools"] for row in public_trace(context)] == [[]]


def test_strip_process_text_keeps_only_the_final_answer():
    """过程解说不能跟着正文落库，否则刷新后历史回看会把解说重显示一遍。"""
    context = _trace_context()
    first = begin_round(context, "run-1")
    record_text(context, first, "我先画一张图。")
    mark_round_process(context, first)
    second = begin_round(context, "run-2")
    record_text(context, second, "再验算一次。")
    mark_round_process(context, second)
    third = begin_round(context, "run-3")
    record_text(context, third, "**解答**：最小值是 4。")
    mark_round_final(context, third)

    body = "我先画一张图。\n\n再验算一次。\n\n**解答**：最小值是 4。"
    assert strip_process_text(context, body) == "**解答**：最小值是 4。"


def test_strip_process_text_gives_up_when_the_body_was_rewritten():
    """对不上原文就整体放弃：宁可和面板重复，也不能吃掉答案。"""
    context = _trace_context()
    current = begin_round(context, "run-1")
    record_text(context, current, "我先画一张图。")
    mark_round_process(context, current)

    body = "我先画了张图。\n\n答案：4"
    assert strip_process_text(context, body) == body


def test_strip_process_text_skips_truncated_rounds():
    """被预算截断的轮只存了前缀，剩下一截不在台账里，剥不干净就整体不动。"""
    context = _trace_context()
    current = begin_round(context, "run-1")
    record_text(context, current, "循" * MAX_ROUND_TEXT_CHARS)
    record_text(context, current, "未入台账的后半句")
    mark_round_process(context, current)

    body = "循" * MAX_ROUND_TEXT_CHARS + "未入台账的后半句\n\n答案：4"
    assert strip_process_text(context, body) == body


def test_strip_process_text_never_empties_the_body():
    """整段都是过程解说（答案轮一个字没产出）时保留原文，不能发空消息。"""
    context = _trace_context()
    current = begin_round(context, "run-1")
    record_text(context, current, "只有过程解说")
    mark_round_process(context, current)

    assert strip_process_text(context, "只有过程解说") == "只有过程解说"


def test_strip_process_text_is_noop_when_trace_is_disabled():
    """受限模式不采纪要，正文一个字也不能动（模式守卫已经守过一道）。"""
    context = _trace_context("hint_only")
    body = "我先画一张图。\n\n提示：先配方。"
    assert strip_process_text(context, body) == body


def test_result_summary_has_no_answer_or_error_text():
    output = ToolOutput(
        success=False,
        error="连接 qdrant://10.0.0.5:6333 失败，题目《二次函数最值》无法检索",
        result="答案：最小值是 4",
        data={"results": [{"content": "题干正文"}, {"content": "题干正文"}]},
        metadata={"error_code": "TOOL_TIMEOUT"},
    )
    summary = summarize_result(output)
    assert "status=failed" in summary
    assert "error_code=TOOL_TIMEOUT" in summary
    assert "results=2" in summary
    assert "最小值" not in summary and "题干正文" not in summary and "qdrant" not in summary


def test_trace_reasoning_flushes_on_the_200ms_time_gate():
    """模型写得慢时不能等凑满 400 字才动：时间闸门也要驱动面板增长。"""
    context = _trace_context()
    round_index = begin_round(context, "run-1")
    record_text(context, round_index, "慢" * 10)

    # 刚开轮：两个闸门都没过
    assert drain_trace_events(context, now=0.0) == []

    flushed = drain_trace_events(context, now=REASONING_BATCH_MS / 1000)
    assert _events_by_type(flushed) == ["reasoning"]
    assert flushed[0]["text"] == "慢" * 10

    # 距上次广播只过了 50ms、又多出 5 个字：不刷屏，等下一个闸门
    record_text(context, round_index, "慢" * 5)
    assert drain_trace_events(context, now=REASONING_BATCH_MS / 1000 + 0.05) == []


@pytest.mark.asyncio
async def test_registry_direct_call_attaches_summary_to_round_zero():
    """多模态识图一类直连调用发生在模型开轮之前，摘要归 round 0，不能丢。"""
    registry = HybridToolRegistry()
    registry.register(_EchoTool())
    context = _trace_context()

    await registry.execute_safe(
        "math_visualize",
        ToolInput(
            query="已知 f(x)=x^2，求最小值",
            parameters={"type": "function_plot", "spec": {"points": [[0, 0], [1, 1]]}},
            context=context,
        ),
    )

    events = drain_trace_events(context)
    assert _events_by_type(events) == ["tool_io"]
    assert events[0]["round"] == 0
    assert events[0]["input_summary"] == "type=function_plot, points=2"
    assert "最小值" not in events[0]["input_summary"]
    assert drain_trace_events(context) == []

    trace = public_trace(context)
    assert trace[0]["round"] == 0 and trace[0]["kind"] == "direct"
    assert trace[0]["tools"][0]["status"] == STATUS_SUCCESS


@pytest.mark.asyncio
async def test_converter_denial_records_stable_code_without_parameters():
    from agent_core.langchain_adapter import LangChainToolConverter

    context = _trace_context("hint_only")
    context[TRACE_ENABLED_KEY] = True  # 单独校验拒绝分支的摘要口径
    converter = LangChainToolConverter()
    converter.set_context(context)
    lc_tool = converter.convert(_DeniedTool())

    await lc_tool.coroutine(query="直接给答案", parameters={"topic": "二次函数最值"})

    events = drain_trace_events(context)
    assert _events_by_type(events) == ["tool_io"]
    assert events[0]["input_summary"] == ""
    assert events[0]["output_summary"] == "code=MODE_TOOL_DENIED"
    assert public_trace(context)[0]["tools"][0]["status"] == STATUS_DENIED


# ---------------------------------------------------------------------------
# 策略层轮次归因：事件流→面板/正文
# ---------------------------------------------------------------------------


def _model_output(tool_calls=None):
    return SimpleNamespace(
        content="",
        tool_calls=tool_calls or [],
        invalid_tool_calls=[],
        usage_metadata={},
        response_metadata={},
    )


def _round_event_source(context):
    """一轮带工具的过程轮 + 一轮给结论的答案轮（工具摘要由适配器写）。"""

    async def events(*args, **kwargs):
        yield {"event": "on_chat_model_start", "run_id": "run-1", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-1",
            "data": {"chunk": SimpleNamespace(content="我先取几个点，再调用绘图工具。")},
        }
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-1",
            "data": {"output": _model_output([{"name": "math_visualize"}])},
        }
        yield {"event": "on_tool_start", "name": "math_visualize", "data": {}}
        begin_call(context, "math_visualize", source="langchain_agent")
        record_tool_io(
            context,
            "math_visualize",
            input_summary="type=function_plot, points=3",
            output_summary="status=ok",
        )
        finish_call(context, "math_visualize", STATUS_SUCCESS, elapsed_ms=210.5)
        yield {"event": "on_tool_end", "name": "math_visualize", "data": {}}
        yield {"event": "on_chat_model_start", "run_id": "run-2", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-2",
            "data": {"chunk": SimpleNamespace(content="图像已生成。")},
        }
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-2",
            "data": {"output": _model_output()},
        }

    return events


def test_strategy_stream_publishes_live_reasoning_before_the_round_is_classified(monkeypatch):
    """长过程轮要让面板实时增长，不能等整轮结束才一次性搬。"""
    context = _trace_context()
    narration = "长" * (REASONING_BATCH_CHARS + 1)

    async def events(*args, **kwargs):
        yield {"event": "on_chat_model_start", "run_id": "run-1", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-1",
            "data": {"chunk": SimpleNamespace(content=narration)},
        }
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-1",
            "data": {"output": _model_output([{"name": "math_visualize"}])},
        }

    chunks = _run_strategy_stream(monkeypatch, events, context)
    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]

    assert _events_by_type(steps) == ["reasoning", "round_process"]
    assert steps[0]["text"] == narration
    # 定性后的 round_process 以全文为准：前端是覆盖不是累加，不会双份
    assert steps[1]["text"] == narration
    assert "".join(chunk for chunk in chunks if isinstance(chunk, str)) == narration


def test_strategy_stream_labels_process_and_final_rounds(monkeypatch):
    context = _trace_context()
    chunks = _run_strategy_stream(monkeypatch, _round_event_source(context), context)
    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]

    assert _events_by_type(steps) == [
        "round_process",
        "tool_start",
        "tool_end",
        "tool_io",
        "round_final",
    ]
    process = steps[0]
    assert process["round"] == 1
    assert process["text"] == "我先取几个点，再调用绘图工具。"
    # 正文一个字不少：搬动由前端按后缀完成，后端不会提前抽走答案文本
    assert "".join(c for c in chunks if isinstance(c, str)) == "我先取几个点，再调用绘图工具。图像已生成。"
    assert [item["kind"] for item in public_trace(context)] == ["process", "final"]


def test_strategy_stream_emits_no_trace_events_in_restricted_mode(monkeypatch):
    """受限模式只给工具时间线：推理文本会绕过只守正文的 mode guard。"""
    context = _trace_context("hint_only")
    chunks = _run_strategy_stream(monkeypatch, _round_event_source(context), context)
    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]

    assert _events_by_type(steps) == ["tool_start", "tool_end"]
    assert _trace_types(steps) == []
    assert TRACE_KEY not in context
    assert public_trace(context) == []


def test_strategy_keeps_round_trace_when_the_model_stream_breaks(monkeypatch):
    """异常路径下已定性的轮次不丢，未定性的按答案轮收尾（不把正文搬进面板）。"""
    context = _trace_context()

    async def broken_events(*args, **kwargs):
        yield {"event": "on_chat_model_start", "run_id": "run-1", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-1",
            "data": {"chunk": SimpleNamespace(content="先算一步")},
        }
        raise RuntimeError("模型断流")

    chunks = _run_strategy_stream(monkeypatch, broken_events, context)
    steps = [chunk for chunk in chunks if isinstance(chunk, dict)]

    assert _events_by_type(steps) == ["round_final"]
    assert "先算一步" in "".join(c for c in chunks if isinstance(c, str))
    assert public_trace(context)[0]["text"] == ""


def test_strategy_closing_does_not_duplicate_unclassified_round_text():
    """收尾排空不能再发一条 reasoning：那段文字已在正文里。"""
    _, closing = _strategy_helpers()
    context = _trace_context()
    round_index = begin_round(context, "run-1")
    record_text(context, round_index, "边说边调工具")

    events = closing(context)

    assert _events_by_type(events) == ["round_final"]
    assert public_trace(context)[0]["kind"] == "final"


def test_strategy_execute_joins_only_answer_text_when_tools_are_called(monkeypatch):
    """非流式入口（solve 一类）拿到的必须是纯正文：时间线事件是字典，不是文本。"""
    context = _trace_context()

    async def events(*args, **kwargs):
        yield {"event": "on_chat_model_start", "run_id": "run-1", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "run_id": "run-1",
            "data": {"chunk": SimpleNamespace(content="开口向上。")},
        }
        yield {"event": "on_tool_start", "name": "math_visualize", "data": {}}
        begin_call(context, "math_visualize", source="langchain_agent")
        record_tool_io(context, "math_visualize", input_summary="type=function_plot")
        finish_call(context, "math_visualize", STATUS_SUCCESS)
        yield {"event": "on_tool_end", "name": "math_visualize", "data": {}}
        yield {
            "event": "on_chat_model_end",
            "run_id": "run-1",
            "data": {"output": _model_output()},
        }

    answer = _run_strategy_execute(monkeypatch, events, context)

    assert answer == "开口向上。"
    assert public_summary(context)[0]["status"] == STATUS_SUCCESS


def test_strategy_execute_still_degrades_when_the_model_fails(monkeypatch):
    """模型报错时原样返回降级文案：事件字典混进 join() 会把兜底一起崩掉。"""
    from agent_core.degradation import degradation_text

    context = _trace_context()

    async def failing_events(*args, **kwargs):
        yield {"event": "on_chat_model_start", "run_id": "run-1", "data": {}}
        raise RuntimeError("模型不可用")

    answer = _run_strategy_execute(monkeypatch, failing_events, context)

    assert answer == degradation_text("model_failure")
    assert public_trace(context)[0]["kind"] == "final"
