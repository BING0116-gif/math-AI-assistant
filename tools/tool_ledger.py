"""工具调用台账 — 让每一次封装工具的调用都能在对话时间线显示，并给出真实终态。

单一漏斗：调用状态只由真正执行工具的两处写入（LangChain 转换器与注册表
execute_safe），展示层只从台账抽取事件，不再依赖 LangChain 回调名字猜成功与否。
台账随请求 context 生命周期存在，不跨学生会话共享，也不记录工具参数或模型输出。

台账同时承担「思考过程纪要」的轮次归因：策略层按模型调用轮登记文本，
工具摘要挂在轮次上，受限模式由 trace_enabled 一次性关掉整条采集。
"""

from __future__ import annotations

import ast
import json
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

LEDGER_KEY = "_tool_ledger"
LEDGER_SEQ_KEY = "_tool_ledger_seq"

# 思考过程纪要：轮次状态与广播游标，与工具台账同生命周期。
TRACE_ENABLED_KEY = "trace_enabled"
TRACE_KEY = "_agent_trace"

# 预算：思考文本可能很长，必须按轮、按总量收敛，否则 SSE 重放缓冲会被撑爆。
MAX_ROUND_TEXT_CHARS = 4000
MAX_TRACE_ROUNDS = 8
MAX_TRACE_TOTAL_CHARS = 24000
REASONING_BATCH_CHARS = 400
# 增量广播的时间闸门：模型写得慢时面板也要按节奏长出来，不能等凑满 400 字才动一下。
REASONING_BATCH_MS = 200
TOOL_IO_SUMMARY_CHARS = 160

# 终态字典：success 之外的都是"调用未成功"，展示与落库共用同一口径。
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_UNAVAILABLE = "unavailable"
STATUS_DENIED = "denied"
STATUS_ABORTED = "aborted"

TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCESS, STATUS_ERROR, STATUS_TIMEOUT, STATUS_UNAVAILABLE, STATUS_DENIED, STATUS_ABORTED}
)

# 内部工具名对学生不可读，展示层统一用中文动作名；未登记的工具回退工具名本身。
TOOL_LABELS: Dict[str, str] = {
    "vision_tool": "图片题目识别",
    "search_questions": "题库检索",
    "recommend_questions": "相似题推荐",
    "skill_profile": "学习画像查询",
    "explain_question": "题目讲解",
    "error_book_analysis": "错题分析",
    "ask_student": "向你追问",
    "math_verify": "数学验证",
    "math_visualize": "函数图像绘制",
    "math_animate": "动画演示",
}

STATUS_MESSAGES: Dict[str, str] = {
    STATUS_SUCCESS: "调用成功",
    STATUS_ERROR: "调用失败",
    STATUS_TIMEOUT: "调用超时",
    STATUS_UNAVAILABLE: "工具暂不可用",
    STATUS_DENIED: "该模式下不可用",
    STATUS_ABORTED: "调用已中断",
}


def tool_label(tool_name: str) -> str:
    """工具的学生可读名称；新工具没登记标签时用工具名兜底，不显示空白。"""
    name = str(tool_name or "")
    return TOOL_LABELS.get(name, name or "工具")


def status_for_error_code(error_code: str) -> str:
    """把守卫/工具返回的稳定错误码映射成展示终态，与指标口径共用一份定义。"""
    return {
        "TOOL_TIMEOUT": STATUS_TIMEOUT,
        "TOOL_UNAVAILABLE": STATUS_UNAVAILABLE,
    }.get(str(error_code or ""), STATUS_ERROR)


def _entries(context: Any) -> Optional[List[Dict[str, Any]]]:
    """取得当前请求的台账列表；context 不是可变字典时返回 None（调用方静默跳过）。"""
    if not isinstance(context, dict):
        return None
    entries = context.get(LEDGER_KEY)
    if entries is None:
        entries = []
        context[LEDGER_KEY] = entries
    return entries


def _elapsed(entry: Dict[str, Any], elapsed_ms: float | None) -> float:
    if elapsed_ms is not None:
        return round(float(elapsed_ms), 1)
    return round((time.perf_counter() - entry["started_at"]) * 1000, 1)


def ensure_ledger(context: Any) -> None:
    """把台账列表预先放进请求上下文。

    ToolInput 是 Pydantic 模型，context 字段会被复制；字典本体复制但内层 list
    仍是同一个对象。因此在创建请求上下文时就种下台账，注册表收到的副本才能写回
    同一个列表，直连调用（如多模态识图）的事件才不会丢。与 mode_tool_denials 同一手法。
    """
    if isinstance(context, dict) and context.get(LEDGER_KEY) is None:
        context[LEDGER_KEY] = []


def begin_call(context: Any, tool_name: str, *, source: str = "agent") -> None:
    """登记一次工具开始。

    同一工具已有进行中的记录时不重复登记：Agent 会为先知的直连调用（vision_tool）
    预先占位，注册表执行时不应再产生第二条时间线。
    """
    entries = _entries(context)
    if entries is None:
        return
    for entry in reversed(entries):
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            return
    seq = int(context.get(LEDGER_SEQ_KEY, 0))
    context[LEDGER_SEQ_KEY] = seq + 1
    entries.append(
        {
            "seq": seq,
            "tool": tool_name,
            "label": tool_label(tool_name),
            "status": STATUS_RUNNING,
            "code": "",
            "elapsed_ms": None,
            "started_at": time.perf_counter(),
            "source": source,
            "start_sent": False,
            "terminal_sent": False,
            "round": current_round(context),
            "input_summary": "",
            "output_summary": "",
            "io_sent": False,
        }
    )


def finish_call(
    context: Any,
    tool_name: str,
    status: str,
    *,
    code: str = "",
    elapsed_ms: float | None = None,
) -> None:
    """写入工具真实终态；没有进行中的记录时补一条，避免调用彻底静默。"""
    entries = _entries(context)
    if entries is None:
        return
    resolved_status = status if status in TERMINAL_STATUSES else STATUS_ERROR
    for entry in reversed(entries):
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            entry["status"] = resolved_status
            entry["code"] = str(code or "")
            entry["elapsed_ms"] = _elapsed(entry, elapsed_ms)
            return
    # 兜底：执行体未经过 begin_call（异常路径或外部工具），仍要留下一次可见记录。
    begin_call(context, tool_name, source="terminal_only")
    for entry in reversed(entries):
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            entry["status"] = resolved_status
            entry["code"] = str(code or "")
            entry["elapsed_ms"] = _elapsed(entry, elapsed_ms)
            return


def mark_start_emitted(context: Any, tool_name: str) -> bool:
    """为工具占位一条“进行中”记录并把开始事件记为已广播。

    LangChain 的 on_tool_start 回调早于工具协程，此时台账还没有条目；
    不预占位就会让终态抽取时再补发一次“正在调用”，时间线出现重复行。
    返回 False 表示同一调用的开始已经广播过，调用方不应再发一次。
    """
    entries = _entries(context)
    if entries is None:
        return False
    for entry in reversed(entries):
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            if entry["start_sent"]:
                return False
            entry["start_sent"] = True
            return True
    begin_call(context, tool_name, source="langchain_callback")
    for entry in reversed(entries):
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            entry["start_sent"] = True
            break
    return True


def close_if_running(
    context: Any, tool_name: str, status: str, *, code: str = ""
) -> bool:
    """只给进行中的记录补终态；已记账的记录不变，避免重复计数。返回是否写了状态。"""
    if not isinstance(context, dict):
        return False
    resolved_status = status if status in TERMINAL_STATUSES else STATUS_ERROR
    for entry in context.get(LEDGER_KEY) or []:
        if entry["tool"] == tool_name and entry["status"] == STATUS_RUNNING:
            entry["status"] = resolved_status
            entry["code"] = str(code or "")
            entry["elapsed_ms"] = _elapsed(entry, None)
            return True
    return False


def close_running(context: Any, status: str = STATUS_ABORTED) -> None:
    """收尾时把所有仍在进行中的记录判定为中断。

    执行流被取消、超时或异常退出时，进行中的记录不会有人再写终态；
    不闭合就会让前端一直转圈并谎报"进行中"。
    """
    if not isinstance(context, dict):
        return
    resolved_status = status if status in TERMINAL_STATUSES else STATUS_ERROR
    for entry in context.get(LEDGER_KEY) or []:
        if entry["status"] == STATUS_RUNNING:
            entry["status"] = resolved_status
            entry["elapsed_ms"] = _elapsed(entry, None)


def drain_events(context: Any) -> List[Dict[str, Any]]:
    """按发生顺序取出尚未广播的 agent_step 事件。

    起始事件与终态事件各只发一次；终态用 tool_end（成功）或 tool_error（未成功），
    与既有 SSE 契约和前端状态机保持一致。
    """
    if not isinstance(context, dict):
        return []
    events: List[Dict[str, Any]] = []
    for entry in context.get(LEDGER_KEY) or []:
        if not entry["start_sent"]:
            entry["start_sent"] = True
            events.append(
                {
                    "__agent_event__": True,
                    "event_type": "tool_start",
                    "tool": entry["tool"],
                    "label": entry["label"],
                    "status": STATUS_RUNNING,
                    "message": f"正在调用：{entry['label']}",
                }
            )
        if entry["status"] != STATUS_RUNNING and not entry["terminal_sent"]:
            entry["terminal_sent"] = True
            succeeded = entry["status"] == STATUS_SUCCESS
            events.append(
                {
                    "__agent_event__": True,
                    "event_type": "tool_end" if succeeded else "tool_error",
                    "tool": entry["tool"],
                    "label": entry["label"],
                    "status": entry["status"],
                    "code": entry["code"],
                    "elapsed_ms": entry["elapsed_ms"],
                    "message": f"{entry['label']}：{STATUS_MESSAGES.get(entry['status'], '已结束')}",
                }
            )
    return events


def has_tool(context: Any, tool_name: str) -> bool:
    """台账是否见过这个工具的调用；只有完全陌生的工具才需要旧格式兜底。"""
    if not isinstance(context, dict):
        return False
    return any(entry["tool"] == tool_name for entry in context.get(LEDGER_KEY) or [])


def public_summary(context: Any) -> List[Dict[str, Any]]:
    """落库用的最小执行轨迹：工具名、可读标签、终态、稳定错误码与耗时。

    只含低基数字段，不含工具参数、题目正文或模型输出，可安全回放到历史消息。
    """
    if not isinstance(context, dict):
        return []
    return [
        {
            "tool": entry["tool"],
            "label": entry["label"],
            "status": entry["status"],
            "code": entry["code"],
            "elapsed_ms": entry["elapsed_ms"],
        }
        for entry in context.get(LEDGER_KEY) or []
    ]


# ── 思考过程纪要：轮次归因与摘要 ────────────────────────────────────────

_UNSAFE_TEXT = re.compile(r"[\r\n\t]+|[\w.+-]+@[\w.-]+|[A-Za-z]:\\[^\s,]+|/[\w.-]{3,}")
# 参数摘要白名单：只保留能说明「做了什么」的低基数事实；query/题干/标题一律排除。
_IO_SCALAR_KEYS = (
    "type",
    "template_id",
    "category",
    "mode",
    "difficulty",
    "limit",
    "top_k",
    "variable",
    "lower",
    "upper",
)
_IO_COUNT_KEYS = ("series", "points", "questions", "results", "items", "frames", "annotations")
# 白名单一个都没命中时只报「带了哪些参数名」：参数值可能是题干原文，键名不是。
_IO_PARAM_NAME_LIMIT = 3
# 这些名字只是「包裹层」（模型把子参数装进去的容器），报出来没有任何信息量。
_GENERIC_IO_KEYS = frozenset(
    {"parameters", "params", "kwargs", "input", "inputs", "args", "spec", "options", "extra", "data", "metadata"}
)
# 模型写的 JSON / Python 字面量长度上限：只对字面量求值，不对任意长文本动手。
# 绘图类的 spec 字符串动辄几 KB（上百个采样点），太小就只能报空，面板里连结构事实都没了。
_IO_LITERAL_EVAL_LIMIT = 8000
_IO_STATUS_KEYS = (
    "visualization_status",
    "animation_status",
    "status",
    "code",
    "error_code",
    "count",
    "total",
    "template_id",
    "verification_type",
)


def _trace_state(context: Any, *, create: bool = True) -> Optional[Dict[str, Any]]:
    """取轮次状态；没采集开关就一律不开。

    trace_enabled 是 fail-closed 开关：只有确认过模式的调用方（agent 的
    _build_context）才能打开，忘记设置的其他入口宁可不采，也不能把逐轮过述
    泄到受限模式的 SSE 与落库里（模式守卫只守正文，拦不住这些文本）。
    """
    if not isinstance(context, dict) or not context.get(TRACE_ENABLED_KEY, False):
        return None
    state = context.get(TRACE_KEY)
    if state is None:
        if not create:
            return None
        state = {"rounds": [], "seq": 0, "runs": {}}
        context[TRACE_KEY] = state
    return state


def _round(state: Dict[str, Any], round_index: int) -> Optional[Dict[str, Any]]:
    for item in state["rounds"]:
        if item["round"] == round_index:
            return item
    return None


def _clip(text: Any, limit: int) -> str:
    """摘要文本去换行、去邮箱与路径痕迹后截断，避免泄露学生数据也避免撑坏布局。"""
    cleaned = _UNSAFE_TEXT.sub(" ", str(text if text is not None else "")).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned[:limit]


def _clock() -> float:
    """纪要节流用的单调时钟；测试里可换成定值，避免断言受真实耗时影响。"""
    return time.perf_counter()


def begin_round(context: Any, run_id: str) -> int:
    """为一次模型调用开一轮；同一 run_id 幂等，返回 1-based 轮号（关闭时为 0）。"""
    state = _trace_state(context)
    if state is None:
        return 0
    known = state["runs"].get(str(run_id))
    if known:
        return int(known)
    state["seq"] = int(state["seq"]) + 1
    index = int(state["seq"])
    state["runs"][str(run_id)] = index
    state["rounds"].append(
        {
            "round": index,
            "text": "",
            "sent_chars": 0,
            "kind": "",
            "kind_sent": False,
            "truncated": False,
            "started_at": time.perf_counter(),
            "elapsed_ms": None,
            # 上一次增量广播的时刻：节流看「够 400 字」或「够 200ms」，任一满足就发。
            "last_reasoning_at": _clock(),
        }
    )
    return index


def round_for_run(context: Any, run_id: str) -> int:
    """按模型调用的 run_id 找回轮号；没登记过（回调丢失）时返回 0。"""
    state = _trace_state(context, create=False)
    if not state:
        return 0
    return int(state["runs"].get(str(run_id), 0))


def current_round(context: Any) -> int:
    """最近一轮的轮号；没有轮次（含受限模式）时返回 0。"""
    state = _trace_state(context, create=False)
    if not state or not state["rounds"]:
        return 0
    return int(state["rounds"][-1]["round"])


def record_text(context: Any, round_index: int, text: str) -> None:
    """累积该轮模型已产出的文本，供节流广播与定性回退时精确搬迁。"""
    if not text:
        return
    state = _trace_state(context)
    if state is None:
        return
    item = _round(state, round_index)
    if item is None:
        return
    if len(item["text"]) >= MAX_ROUND_TEXT_CHARS:
        item["truncated"] = True
        return
    room = MAX_ROUND_TEXT_CHARS - len(item["text"])
    item["text"] += str(text)[:room]
    if len(str(text)) > room:
        item["truncated"] = True


def _classify(context: Any, round_index: int, kind: str) -> None:
    state = _trace_state(context)
    if state is None:
        return
    item = _round(state, round_index)
    if item is None:
        return
    item["kind"] = kind
    # 定性之后该轮文本由 round_process 整体携带，或留在正文（final 轮），
    # 游标推到底可以避免再发一条内容重复的 reasoning 事件。
    item["sent_chars"] = len(item["text"])
    item["elapsed_ms"] = round((time.perf_counter() - item["started_at"]) * 1000, 1)


def mark_round_process(context: Any, round_index: int) -> None:
    """该轮调用了工具 → 属于过程轮，其文本归思考面板。"""
    _classify(context, round_index, "process")


def mark_round_final(context: Any, round_index: int) -> None:
    """该轮没有工具调用 → 属于答案轮，其文本留在正文，面板不重复显示。"""
    _classify(context, round_index, "final")


def close_open_rounds(context: Any) -> None:
    """收尾时把尚未定性的轮次按答案轮处理。

    超时或模型只发了半轮时无法判断这轮会不会调工具，按答案轮处理最保守：
    文本已经流进正文，既不会再往面板搬一次，也不会让正文丢字。
    """
    state = _trace_state(context, create=False)
    if not state:
        return
    for item in state["rounds"]:
        if not item["kind"]:
            _classify(context, item["round"], "final")


# 剥掉过程轮之后可能留下多余空行，压回一个段落分隔。
_ROUND_GAP_RE = re.compile(r"\n{3,}")


def strip_process_text(context: Any, body: str) -> str:
    """把过程轮的解说文本从答案正文里剥掉，让落库正文只留最终答案。

    流式阶段前端已经按 round_process 把解说搬进面板，但正文本身仍是
    「过程解说 + 最终答案」的拼接；不剥掉的话，刷新页面走历史回看会把解说
    又在正文里显示一遍，和面板重复。

    剥离只在台账确实开了采集时生效，并按轮次顺序单调匹配原文：
    任一轮对不上（正文被模式守卫重写过、文本截断过、供应商改写过空白）
    就整体放弃，宁可和面板重复一份，也不能吃掉答案正文。
    """
    if not isinstance(body, str) or not body:
        return body
    state = _trace_state(context, create=False)
    if state is None:
        return body
    stripped = body
    cursor = 0
    for item in sorted(state["rounds"], key=lambda entry: entry["round"]):
        if item["kind"] != "process" or not item["text"] or item["truncated"]:
            continue
        text = item["text"]
        index = stripped.find(text, cursor)
        if index < 0:
            return body
        stripped = stripped[:index] + stripped[index + len(text) :]
        cursor = index
    if stripped == body:
        return body
    cleaned = _ROUND_GAP_RE.sub("\n\n", stripped).strip()
    # 正文整段都是过程解说时（答案轮一个字没产出）保留原样，不能把消息清空。
    return cleaned or body


def _is_container(value: Any) -> bool:
    """字典/列表一类「还要往下拆」的值；字符串不算（参数值就是干词）。"""
    return isinstance(value, Mapping) or (isinstance(value, Sequence) and not isinstance(value, (str, bytes)))


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    """取结构体，三种来源都要能拆：真字典、模型写成的 JSON / Python 字面量字符串，
    以及 LangChain 按 args_schema 校验后原样交给工具的 Pydantic 模型实例。

    最后一种最容易漏：适配器拿到的是 `getattr(result, k)` 的字段值，嵌套入参
    （绘图 spec 一类）根本不是 dict 也不是字符串。不拆开就只能看见 parameters
    这个包裹层名字，而它按规则不该外报，于是整行入参摘要退化成空。
    """
    if isinstance(value, Mapping):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            dumped = dump(exclude_none=True)
        except Exception:  # 摘要失败不能拖垮工具调用
            return None
        if isinstance(dumped, Mapping):
            return dumped
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("{") or len(text) > _IO_LITERAL_EVAL_LIMIT:
            return None
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            # json 解不了的单引号写法：只走 literal_eval，不执任何表达式。
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                return None
        if isinstance(parsed, Mapping):
            return parsed
    return None


def summarize_parameters(raw: Any) -> str:
    """把工具参数收敛成「键名 + 白名单标量 + 数量」的可审计摘要。

    工具参数里可能带题干原文、学生输入或模型自述，一律不进摘要；
    只保留足以让学生明白「这次调用做了什么」的结构事实。
    """
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return f"count={len(raw)}"
    if not isinstance(raw, Mapping):
        return ""
    node: Mapping[str, Any] = raw
    nested = _as_mapping(node.get("parameters"))
    if nested is not None:
        node = nested
    spec = _as_mapping(node.get("spec"))
    parts: List[str] = []
    for key in _IO_SCALAR_KEYS:
        value = node.get(key)
        if isinstance(value, (bool, int, float)) or isinstance(value, str):
            clipped = _clip(value, 40)
            if clipped:
                parts.append(f"{key}={clipped}")
    for key in _IO_COUNT_KEYS:
        value = spec.get(key) if isinstance(spec, Mapping) else node.get(key)
        # 空列表不报：annotations=0 这类事实只吃摘要预算，不告诉学生任何新东西。
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value):
            parts.append(f"{key}={len(value)}")
    # 采样点也可能只挂在 series 里（每条曲线各自带 points）。
    if isinstance(spec, Mapping) and not any(part.startswith("points=") for part in parts):
        series = spec.get("series")
        if isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
            sampled = sum(
                len(item.get("points") or [])
                for item in series
                if isinstance(item, Mapping)
            )
            if sampled:
                parts.append(f"points={sampled}")
    if not parts and node:
        # 只剩 query/题干一类不可外发的参数：至少让学生看到“这次带了什么入参”，键名不是隐私，值才是。
        # 但只拿到 parameters 这类包裹层名字时宁可不报：报个空壳词比不报更让人误解。
        names = sorted(str(key) for key in node)
        plain = [key for key in names if not _is_container(node.get(key))]
        informative = [key for key in (plain or names) if key.lower() not in _GENERIC_IO_KEYS]
        chosen = informative[:_IO_PARAM_NAME_LIMIT]
        if chosen:
            parts.append("params=" + ",".join(chosen))
    return _clip(", ".join(dict.fromkeys(parts)), TOOL_IO_SUMMARY_CHARS)


def _status_facts(node: Mapping[str, Any]) -> List[str]:
    """从一个结构体里挑白名单事实：状态字符串、开关量与序列长度。"""
    facts: List[str] = []
    for key in _IO_STATUS_KEYS:
        value = node.get(key)
        if isinstance(value, bool):
            facts.append(f"{key}={str(value).lower()}")
        elif isinstance(value, (int, float)) or isinstance(value, str):
            clipped = _clip(value, 40)
            if clipped:
                facts.append(f"{key}={clipped}")
    for key in _IO_COUNT_KEYS:
        value = node.get(key)
        # 结果侧的空列表照报：“检索到 0 条”本身是结论；入参侧的空字段只是没填。
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            facts.append(f"{key}={len(value)}")
    verification = node.get("verification")
    if isinstance(verification, Mapping) and verification.get("status"):
        facts.append(f"verification={_clip(verification['status'], 40)}")
    return facts


def summarize_result(output: Any) -> str:
    """从工具结果里挑低基数事实（状态、命中数量、验证结论），不回传结果本体。

    ToolOutput.result 里常常是题号、题干摘要或模型写的自然语言，一律不进面板；
    只从 metadata 与 data 这两个结构体取事实，失败分支因此只能看到 error_code。
    """
    if output is None:
        return ""
    nodes: List[Mapping[str, Any]] = []
    if isinstance(output, Mapping):
        nodes.append(output)
        success = output.get("success")
    else:
        success = getattr(output, "success", None)
    for key in ("metadata", "data"):
        child = output.get(key) if isinstance(output, Mapping) else getattr(output, key, None)
        if isinstance(child, Mapping):
            nodes.append(child)
    facts: List[str] = []
    if isinstance(success, bool):
        facts.append("status=" + ("ok" if success else "failed"))
    for node in nodes:
        facts.extend(_status_facts(node))
    return _clip(", ".join(dict.fromkeys(facts)), TOOL_IO_SUMMARY_CHARS)


def _io_target(entries: List[Dict[str, Any]], tool_name: str) -> Optional[Dict[str, Any]]:
    for entry in reversed(entries):
        if entry["tool"] == tool_name:
            return entry
    return None


def record_tool_io(
    context: Any,
    tool_name: str,
    *,
    input_summary: str = "",
    output_summary: str = "",
) -> None:
    """给某次工具调用挂上输入/输出摘要；已广播的条目不再改写。"""
    if not isinstance(context, dict) or not context.get(TRACE_ENABLED_KEY, False):
        return
    entries = context.get(LEDGER_KEY)
    if not entries:
        return
    entry = _io_target(entries, tool_name)
    if entry is None or entry.get("io_sent"):
        return
    if input_summary:
        entry["input_summary"] = _clip(input_summary, TOOL_IO_SUMMARY_CHARS)
    if output_summary:
        entry["output_summary"] = _clip(output_summary, TOOL_IO_SUMMARY_CHARS)


def _io_facts(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": entry["tool"],
        "label": entry["label"],
        "status": entry["status"],
        "code": entry["code"],
        "elapsed_ms": entry["elapsed_ms"],
        "input_summary": entry["input_summary"],
        "output_summary": entry["output_summary"],
    }


def _pending_loose_io(entries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """取出不属于任何模型轮次的工具摘要（多模态识图等直连调用）。"""
    pending = [
        entry
        for entry in entries
        if not entry.get("round") and not entry.get("io_sent") and _io_is_visible(entry)
    ]
    for entry in pending:
        entry["io_sent"] = True
    return pending


def _io_is_visible(entry: Dict[str, Any]) -> bool:
    """该次调用是否值得占一行面板。

    没摘要的成功调用可以不提；但任何没成功的调用都要提，哪怕一行摘要也组不出来：
    否则“模型把参数写错、被 LangChain 提前拦下”这类事只会刷新后才从落库数据里
    突然多出一行，与流式期间的面板不一致。
    """
    if entry.get("input_summary") or entry.get("output_summary"):
        return True
    return entry.get("status") not in (None, "", STATUS_SUCCESS)


def drain_trace_events(
    context: Any, *, force: bool = False, now: Optional[float] = None
) -> List[Dict[str, Any]]:
    """按轮次取出尚未广播的纪要事件。

    正文与面板共用同一条 agent_step 通道：reasoning 是「尚未定性」的临时面板内容，
    round_process 表示该轮文本要从正文搬进面板，round_final 表示该轮就是答案、
    面板撤掉临时内容。工具摘要（tool_io）挂在所属轮次之后。

    一轮都没开（多模态直连识图）时也要能排空 round 0 的工具摘要，
    所以这里不能用「轮次状态存在吗」当闸门。

    `now` 只给测试用：真实调用走 `_clock()`，注入固定时刻才能稳定断言时间闸门。
    """
    if not isinstance(context, dict) or not context.get(TRACE_ENABLED_KEY, False):
        return []
    state = _trace_state(context, create=False)
    stamp = _clock() if now is None else float(now)
    events: List[Dict[str, Any]] = []
    entries = context.get(LEDGER_KEY) or []
    for item in state["rounds"] if state else []:
        delta = item["text"][item["sent_chars"] :]
        # 0.0 也是合法时刻，不能用 or 兼容没登记的轮：那样会把时间闸门关掉。
        last_reasoning_at = item.get("last_reasoning_at")
        idle_ms = 0.0 if last_reasoning_at is None else (stamp - float(last_reasoning_at)) * 1000
        if delta and (force or len(delta) >= REASONING_BATCH_CHARS or idle_ms >= REASONING_BATCH_MS):
            item["sent_chars"] = len(item["text"])
            item["last_reasoning_at"] = stamp
            events.append(
                {
                    "__agent_event__": True,
                    "event_type": "reasoning",
                    "round": item["round"],
                    "text": delta,
                    "truncated": bool(item["truncated"]),
                }
            )
        if item["kind"] and not item["kind_sent"]:
            item["kind_sent"] = True
            if item["kind"] == "process":
                events.append(
                    {
                        "__agent_event__": True,
                        "event_type": "round_process",
                        "round": item["round"],
                        "text": item["text"],
                        "elapsed_ms": item["elapsed_ms"],
                        "truncated": bool(item["truncated"]),
                    }
                )
            else:
                events.append(
                    {
                        "__agent_event__": True,
                        "event_type": "round_final",
                        "round": item["round"],
                        "elapsed_ms": item["elapsed_ms"],
                    }
                )
        for entry in entries:
            if entry.get("round") != item["round"] or entry.get("io_sent"):
                continue
            if not _io_is_visible(entry):
                continue
            entry["io_sent"] = True
            events.append(
                {
                    "__agent_event__": True,
                    "event_type": "tool_io",
                    "round": item["round"],
                    "tool": entry["tool"],
                    "label": entry["label"],
                    "status": entry["status"],
                    "code": entry["code"],
                    "elapsed_ms": entry["elapsed_ms"],
                    "input_summary": entry["input_summary"],
                    "output_summary": entry["output_summary"],
                }
            )
    for entry in _pending_loose_io(entries):
        events.append(
            {
                "__agent_event__": True,
                "event_type": "tool_io",
                "round": 0,
                "tool": entry["tool"],
                "label": entry["label"],
                "status": entry["status"],
                "code": entry["code"],
                "elapsed_ms": entry["elapsed_ms"],
                "input_summary": entry["input_summary"],
                "output_summary": entry["output_summary"],
            }
        )
    return events


def public_trace(context: Any) -> List[Dict[str, Any]]:
    """落库用的有界思考纪要。

    答案轮文本不重复存（正文已落库），过程轮文本按轮、按总量截断；
    工具摘要只含白名单结构事实，不含参数原文。
    """
    if not isinstance(context, dict) or not context.get(TRACE_ENABLED_KEY, False):
        return []
    state = _trace_state(context, create=False)
    rounds = list(state["rounds"]) if state else []
    if len(rounds) > MAX_TRACE_ROUNDS:
        keep = rounds[: MAX_TRACE_ROUNDS - 3] + rounds[-3:]
    else:
        keep = list(rounds)
    entries = context.get(LEDGER_KEY) or []
    payload: List[Dict[str, Any]] = []
    # 直连调用（如多模态识图）发生在模型开轮之前，单独归到 round 0，否则面板会丢工具。
    loose = [
        entry
        for entry in entries
        if not entry.get("round") and _io_is_visible(entry)
    ]
    if loose:
        payload.append(
            {
                "round": 0,
                "kind": "direct",
                "text": "",
                "elapsed_ms": None,
                "truncated": False,
                "tools": [_io_facts(entry) for entry in loose],
            }
        )
    used = 0
    for item in keep:
        tools = [
            _io_facts(entry)
            for entry in entries
            if entry.get("round") == item["round"] and _io_is_visible(entry)
        ]
        text = item["text"] if item["kind"] == "process" else ""
        room = max(0, MAX_TRACE_TOTAL_CHARS - used)
        if len(text) > room:
            text = text[:room]
            item["truncated"] = True
        used += len(text)
        payload.append(
            {
                "round": item["round"],
                "kind": item["kind"],
                "text": text,
                "elapsed_ms": item["elapsed_ms"],
                "truncated": bool(item["truncated"]),
                "tools": tools,
            }
        )
    if len(rounds) > len(keep):
        payload.insert(0, {"round": 0, "kind": "omitted", "text": "", "elapsed_ms": None, "truncated": True, "tools": []})
    return payload
