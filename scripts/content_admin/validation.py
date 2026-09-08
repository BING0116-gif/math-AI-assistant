"""validation.py — Step 1.1-D 审核工具的纯逻辑 helpers（无 streamlit / 无 IO，可单测）。

提供：
- 显示标签（parser / batch status / candidate status / question status）
- 题型支持判定（首版支持 choice / judge / numeric_fill / expression_fill）
- blocking warnings 判定（在 UI 端复用服务端同一套语义的启发式，用于置灰 Publish）
- 人工审核 checklist 状态（全部勾选才允许 Mark Reviewed）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 与后端 SUPPORTED_TYPES 保持一致（扩展后可入库题型）
SUPPORTED_TYPES = {"choice", "judge", "numeric_fill", "expression_fill", "calculation", "proof", "short_answer"}

TYPE_LABELS = {
    "choice": "选择题",
    "judge": "判断题",
    "numeric_fill": "数值填空题",
    "expression_fill": "表达式填空题",
    "fill_candidate": "填空题（待人工判定）",
    "fill": "填空题（待人工判定）",
    "calculation": "计算题",
    "proof": "证明题",
    "short_answer": "简答题",
    "subjective": "主观题",
    "text": "文本（待定）",
}

PARSER_LABELS = {"quick": "Quick 解析", "mineru": "MinerU"}

BATCH_STATUS_LABELS = {
    "pending": "待解析",
    "parsing": "解析中",
    "parsed": "已解析",
    "completed": "已完成",
    "failed": "失败",
}

CANDIDATE_STATUS_LABELS = {
    "parsed": "已解析",
    "edited": "已编辑",
    "imported": "已转正式题",
    "rejected": "已拒绝",
}

QUESTION_STATUS_LABELS = {
    "draft": "草稿",
    "reviewed": "已审核",
    "published": "已发布",
    "retired": "已下线",
}


def parser_display_name(parser_name: Optional[str]) -> str:
    return PARSER_LABELS.get(parser_name or "", parser_name or "未知")


def batch_status_label(status: Optional[str]) -> str:
    return BATCH_STATUS_LABELS.get(status or "", status or "未知")


def candidate_status_label(status: Optional[str]) -> str:
    return CANDIDATE_STATUS_LABELS.get(status or "", status or "未知")


def question_status_label(status: Optional[str]) -> str:
    return QUESTION_STATUS_LABELS.get(status or "", status or "未知")


def type_display_name(qtype: Optional[str]) -> str:
    return TYPE_LABELS.get(qtype or "", qtype or "未知")


def is_unsupported(qtype: Optional[str]) -> bool:
    """计算题/证明题/主观题 属于首版 UNSUPPORTED。"""
    return (qtype or "") not in SUPPORTED_TYPES


def is_supported(qtype: Optional[str]) -> bool:
    return (qtype or "") in SUPPORTED_TYPES


def blocking_warnings(
    candidate: Optional[Dict[str, Any]],
    question: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """依据 candidate warnings 与当前内容启发式判定仍阻塞的 warning。

    与后端服务端校验尽量一致；最终以服务端返回为准（UI 只是置灰/提示）。
    """
    warnings = (candidate or {}).get("warnings") or []
    blocking = []
    q = question or {}
    qtype = q.get("question_type") or (candidate or {}).get("detected_question_type") or ""

    for w in warnings:
        if w == "option_parse_uncertain":
            options = q.get("options")
            if not _choice_options_ok(options):
                blocking.append(w)
        elif w == "possible_answer_leak":
            blocking.append(w)  # UI 只提示，服务端精确判定
        elif w in (
            "answer_match_missing",
            "answer_match_key_incomplete",
            "answer_roster_incomplete",
            "choice_answer_ambiguous",
        ):
            if not (q.get("answer") or "").strip():
                blocking.append(w)
        elif w == "fill_type_needs_review":
            if qtype == "fill":
                blocking.append(w)
        elif w == "page_mapping_uncertain":
            cand = candidate or {}
            if not cand.get("source_page_start") or not cand.get("source_page_end"):
                blocking.append(w)
        # contains_subquestions 不作为阻塞（与服务端一致）：splitter 启发式会误判
        # 求导记号 f'(1)，保留在 warnings 中作为提示，由审核员左右对照确认。
    return sorted(set(blocking))


def _choice_options_ok(options: Any) -> bool:
    if not isinstance(options, list) or len(options) < 2:
        return False
    for opt in options:
        if not isinstance(opt, dict):
            return False
        if not str(opt.get("id", "")).strip() or not str(opt.get("text", "")).strip():
            return False
    return True


# ── 人工审核 checklist（§34，UI 确认，不落库）──
REVIEW_CHECKLIST = [
    "题干与原 PDF 一致",
    "数学公式 / LaTeX 正确",
    "答案正确",
    "解析正确",
    "知识点正确",
    "题型正确",
    "难度合理",
]

CHECKLIST_KEYS = [
    "stem_matches_pdf",
    "latex_correct",
    "answer_correct",
    "analysis_correct",
    "kp_correct",
    "type_correct",
    "difficulty_reasonable",
]


def checklist_ready(checked: Dict[str, bool]) -> bool:
    return all(checked.get(k, False) for k in CHECKLIST_KEYS)


def render_candidate_preview(candidate: Dict[str, Any]) -> Dict[str, str]:
    """把 candidate 组装成左右对照需要的显示块（纯函数，供 UI / 测试复用）。"""
    qtype = candidate.get("detected_question_type") or "text"
    return {
        "source_question_number": str(candidate.get("source_question_number") or ""),
        "type_display": type_display_name(qtype),
        "supported": "支持" if is_supported(qtype) else "不支持",
        "stem": candidate.get("stem") or "",
        "options": _format_options(candidate.get("options")),
        "answer": candidate.get("original_answer") or "",
        "solution": candidate.get("original_solution") or "",
        "page": _format_page(candidate),
    }


def _format_options(options: Any) -> str:
    return format_options_text(options)


def format_options_text(options: Any) -> str:
    """[{id, text}, ...] -> 'A. xxx\\nB. yyy'（编辑框文本，可回填 parse）。"""
    if not isinstance(options, list):
        return ""
    lines = []
    for opt in options:
        if isinstance(opt, dict):
            lines.append(f"{opt.get('id', '')}. {opt.get('text', '')}")
        else:
            lines.append(str(opt))
    return "\n".join(lines)


def parse_options_text(text: str) -> List[Dict[str, str]]:
    """'A. xxx\\nB. yyy' -> [{id, text}, ...]。无法解析的行跳过；无有效选项返回 []。"""
    if not text:
        return []
    options: List[Dict[str, str]] = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) >= 2 and line[0].isalpha() and line[1] in ".．、":
            options.append({"id": line[0].upper(), "text": line[2:].strip()})
    return options


def _format_page(candidate: Dict[str, Any]) -> str:
    start = candidate.get("source_page_start")
    end = candidate.get("source_page_end")
    if start is None or start == "":
        return "未知页码"
    if end is not None and end != start:
        return f"第 {start}–{end} 页（跨页）"
    return f"第 {start} 页"


# ══════════════════════════════════════════════════════════════════
# AI Analysis 阶段标签 / 徽章（Step 1.1-E2-A0）
# ══════════════════════════════════════════════════════════════════
AI_RUN_STATUS_LABELS = {
    "pending": "待运行",
    "analyzing": "分析中",
    "validating": "校验中",
    "verifying": "验证中",
    "pass": "通过",
    "doubtful": "存疑",
    "failed": "失败",
}

AI_GATE_LABELS = {
    "PASS": "✅ 通过 PASS",
    "DOUBTFUL": "⚠️ 存疑 DOUBTFUL",
    "FAILED": "❌ 失败 FAILED",
}

AI_DISPOSITION_LABELS = {
    "approved": "✅ 通过",
    "doubtful": "⚠️ 存疑",
    "reject": "❌ 拒绝",
    "reanalyze": "🔄 重新分析",
}

PROVIDER_LABELS = {
    "mock": "🧪 MOCK AI",
    "qwen": "🤖 Qwen",
    "none": "无（不可用）",
}

# 各 AI 状态对应的 streamlit 徽章颜色（color arg）
AI_RUN_STATUS_COLOR = {
    "pending": "gray",
    "analyzing": "blue",
    "validating": "blue",
    "verifying": "blue",
    "pass": "green",
    "doubtful": "orange",
    "failed": "red",
}

AI_GATE_COLOR = {
    "PASS": "green",
    "DOUBTFUL": "orange",
    "FAILED": "red",
}


def ai_run_status_label(status: Optional[str]) -> str:
    return AI_RUN_STATUS_LABELS.get(status or "", status or "未知")


def ai_gate_label(gate: Optional[str]) -> str:
    return AI_GATE_LABELS.get(gate or "", gate or "—")


def ai_disposition_label(disposition: Optional[str]) -> str:
    return AI_DISPOSITION_LABELS.get(disposition or "", disposition or "—")


def ai_provider_label(provider: Optional[str]) -> str:
    return PROVIDER_LABELS.get(provider or "", provider or "未知")


def ai_run_status_color(status: Optional[str]) -> str:
    return AI_RUN_STATUS_COLOR.get(status or "", "gray")


def ai_gate_color(gate: Optional[str]) -> str:
    return AI_GATE_COLOR.get(gate or "", "gray")
