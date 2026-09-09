"""Tutor 模式的集中工具策略与输出守卫（T06）。"""

from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional

logger = logging.getLogger(__name__)

CANONICAL_TUTOR_MODES = frozenset({"tutor_free", "hint_only", "guided", "review"})
LEGACY_MODE_ALIASES = {
    "step_by_step": "guided",
    "check_my_work": "review",
}

# T06 单一策略源。allow="*" 表示不裁剪；其余模式使用显式白名单，deny 用于
# 文档与审计，执行决策始终以 allow 为准，避免新增工具默认越权。
MODE_TOOL_POLICY: dict[str, dict[str, Any]] = {
    "tutor_free": {"allow": "*", "deny": frozenset()},
    "hint_only": {
        "allow": frozenset({"vision_tool", "search_questions", "recommend_questions", "skill_profile", "ask_student", "math_visualize"}),
        "deny": frozenset({"explain_question", "error_book_analysis", "math_verify"}),
    },
    "guided": {
        "allow": frozenset({"vision_tool", "search_questions", "recommend_questions", "skill_profile", "ask_student", "math_verify", "math_visualize"}),
        "deny": frozenset({"explain_question", "error_book_analysis"}),
    },
    "review": {
        "allow": frozenset({"vision_tool", "search_questions", "skill_profile", "ask_student", "math_verify", "math_visualize", "error_book_analysis"}),
        "deny": frozenset({"explain_question", "recommend_questions"}),
    },
}

MODE_TOOL_DENIED_CODE = "MODE_TOOL_DENIED"
MODE_TOOL_DENIED_MESSAGE = "该模式下此操作不可用"

_FINAL_ANSWER_PATTERN = re.compile(
    r"(?:\*{0,2}(?:最终答案|完整解答|答案|结论)\*{0,2}\s*[：:]|"
    r"(?:因此|所以|故)\s*(?:可得|解得)?\s*[A-Za-z\u4e00-\u9fff]*\s*=\s*[-+]?\d)",
    re.IGNORECASE,
)
_DIRECT_SOLUTION_PATTERN = re.compile(
    r"(?:解得|根为|解集为|最终得到)\s*[:：]?\s*(?:[A-Za-z]\s*=|\{|[-+]?\d)",
    re.IGNORECASE,
)
_FINAL_CONCLUSION_PATTERN = re.compile(
    r"(?:最终|最后)\s*(?:可以|可)?\s*(?:得到|得出|结果|答案|结论)",
    re.IGNORECASE,
)
_NUMBERED_STEP_PATTERN = re.compile(r"(?m)^\s*(?:第?[一二三四五六七八九十\d]+步|\d+[.、)])")
_LATER_STEP_PATTERN = re.compile(
    r"(?:第\s*(?:二|三|四|五|六|七|八|九|十|[2-9]|\d{2,})\s*步|"
    r"步骤\s*(?:二|三|四|五|六|七|八|九|十|[2-9]|\d{2,}))",
    re.IGNORECASE,
)
_EQUALITY_TOKEN_PATTERN = re.compile(r"(?:=|⇒|=>|⟹|\\Rightarrow)")

CONTROLLED_MODE_RESPONSES = {
    "hint_only": "该回答超出了“只给提示”模式，我不会直接展示完整答案。请先写出你准备采用的定义或第一步变形，我再给下一条提示。",
    "guided": "该回答一次透露了过多步骤。请先完成当前一步，我会在你回复后继续下一步。",
    "review": "该回答超出了“检查思路”模式。请先提交你的推导过程，我会指出第一个需要修正的位置。",
}


def normalize_tutor_mode(mode: str | None) -> str:
    normalized = str(mode or "guided").strip().lower()
    normalized = LEGACY_MODE_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_TUTOR_MODES:
        raise ValueError(f"unsupported tutor mode: {mode}")
    return normalized


def is_guarded_mode(mode: str | None) -> bool:
    return normalize_tutor_mode(mode) != "tutor_free"


def is_tool_allowed(mode: str | None, tool_name: str) -> bool:
    policy = MODE_TOOL_POLICY[normalize_tutor_mode(mode)]
    allowed = policy["allow"]
    return allowed == "*" or tool_name in allowed


def filter_tools_for_mode(tools: Iterable[Any], mode: str | None) -> list[Any]:
    return [tool for tool in tools if is_tool_allowed(mode, str(getattr(tool, "name", "")))]


def tool_denied_payload(mode: str | None, tool_name: str) -> dict[str, str]:
    try:
        canonical = normalize_tutor_mode(mode)
    except ValueError:
        canonical = "invalid"
    return {
        "code": MODE_TOOL_DENIED_CODE,
        "message": MODE_TOOL_DENIED_MESSAGE,
        "mode": canonical,
        "tool_name": tool_name,
    }


@dataclass(frozen=True)
class OutputInspection:
    violates: bool
    signals: tuple[str, ...] = ()
    judged: bool = False


@dataclass(frozen=True)
class GuardedOutput:
    text: str
    allowed: bool
    rewritten: bool
    rewrite_count: int
    signals: tuple[str, ...] = ()
    judge_used: bool = False


JudgeCallback = Callable[[str, str, str], bool | Awaitable[bool]]
RewriteCallback = Callable[[str, str, str, tuple[str, ...]], str | Awaitable[str]]


def inspect_mode_output(mode: str | None, text: str, user_input: str = "") -> OutputInspection:
    """规则优先检测；不尝试判断数学真伪，只识别明显越界的回答形态。"""
    canonical = normalize_tutor_mode(mode)
    if canonical == "tutor_free":
        return OutputInspection(False)

    candidate = str(text or "")
    signals: list[str] = []
    if _FINAL_ANSWER_PATTERN.search(candidate):
        signals.append("final_answer_marker")
    if _DIRECT_SOLUTION_PATTERN.search(candidate):
        signals.append("direct_solution")
    if _FINAL_CONCLUSION_PATTERN.search(candidate):
        signals.append("final_conclusion")
    if len(_EQUALITY_TOKEN_PATTERN.findall(candidate)) >= 2:
        signals.append("complete_equation_chain")
    if canonical in {"hint_only", "guided"} and _LATER_STEP_PATTERN.search(candidate):
        signals.append("later_step_disclosure")

    step_count = len(_NUMBERED_STEP_PATTERN.findall(candidate))
    if canonical in {"hint_only", "guided"} and step_count >= (2 if canonical == "hint_only" else 3):
        signals.append("too_many_steps")

    # review 模式没有学生过程时，完整解题结构同样不得代做。
    if canonical == "review" and not _looks_like_student_work(user_input) and step_count >= 2:
        signals.append("review_without_student_work")
    return OutputInspection(bool(signals), tuple(dict.fromkeys(signals)))


async def guard_mode_output(
    mode: str | None,
    text: str,
    *,
    user_input: str = "",
    judge: Optional[JudgeCallback] = None,
    rewrite: Optional[RewriteCallback] = None,
) -> GuardedOutput:
    """守卫输出；违规时最多重写一次，二次违规绝不原样放行。"""
    canonical = normalize_tutor_mode(mode)
    if canonical == "tutor_free":
        return GuardedOutput(str(text or ""), True, False, 0)

    first = await _inspect_with_optional_judge(canonical, str(text or ""), user_input, judge)
    if not first.violates:
        return GuardedOutput(str(text or ""), True, False, 0, first.signals, first.judged)

    if rewrite is not None:
        try:
            revised = rewrite(canonical, user_input, str(text or ""), first.signals)
            if inspect.isawaitable(revised):
                revised = await revised
            revised_text = str(revised or "")
            second = await _inspect_with_optional_judge(canonical, revised_text, user_input, judge)
            if revised_text.strip() and not second.violates:
                return GuardedOutput(
                    revised_text,
                    True,
                    True,
                    1,
                    tuple(dict.fromkeys(first.signals + second.signals)),
                    first.judged or second.judged,
                )
            signals = tuple(dict.fromkeys(first.signals + second.signals))
            judge_used = first.judged or second.judged
        except Exception as exc:
            logger.warning("模式输出重写失败，返回受控提示: mode=%s error=%s", canonical, type(exc).__name__)
            signals, judge_used = first.signals + ("rewrite_error",), first.judged
    else:
        signals, judge_used = first.signals, first.judged

    return GuardedOutput(
        CONTROLLED_MODE_RESPONSES[canonical],
        False,
        rewrite is not None,
        1 if rewrite is not None else 0,
        signals,
        judge_used,
    )


async def _inspect_with_optional_judge(
    mode: str,
    text: str,
    user_input: str,
    judge: Optional[JudgeCallback],
) -> OutputInspection:
    rule_result = inspect_mode_output(mode, text, user_input)
    if rule_result.violates or judge is None:
        return rule_result
    try:
        judged = judge(mode, user_input, text)
        if inspect.isawaitable(judged):
            judged = await judged
        if bool(judged):
            return OutputInspection(True, ("llm_judge",), True)
        return OutputInspection(False, (), True)
    except Exception as exc:
        # 规则已通过时 judge 不可用不应中断主回复；记录 warning 便于运维。
        logger.warning("模式输出 judge 不可用，使用规则结果: mode=%s error=%s", mode, type(exc).__name__)
        return rule_result


def _looks_like_student_work(user_input: str) -> bool:
    text = str(user_input or "")
    return bool(
        re.search(r"(?:我的|我算|我写|步骤|推导|思路|检查|哪里错|对吗|=|⇒|=>)", text)
        and len(text.strip()) >= 8
    )
