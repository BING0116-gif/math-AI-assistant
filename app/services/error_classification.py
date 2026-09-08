"""Stable, auditable error classification for deterministic question grading."""
from __future__ import annotations

from enum import Enum
from typing import Any

CLASSIFICATION_VERSION = "error-taxonomy-v1"


class ErrorCategory(str, Enum):
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    CONCEPT_MISUNDERSTANDING = "CONCEPT_MISUNDERSTANDING"
    CONDITION_MISSING = "CONDITION_MISSING"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    METHOD_SELECTION = "METHOD_SELECTION"
    FORMULA_MISUSE = "FORMULA_MISUSE"
    CARELESS = "CARELESS"
    UNKNOWN = "UNKNOWN"


def _empty(answer: Any) -> bool:
    return answer is None or (isinstance(answer, str) and not answer.strip())


def _matched_mistake(snapshot: dict[str, Any], answer: Any) -> dict[str, Any] | None:
    """Use only author-reviewed structured mistakes; never infer a cause from a wrong value."""
    for mistake in snapshot.get("common_mistakes") or []:
        if not isinstance(mistake, dict) or str(mistake.get("answer", "")) != str(answer):
            continue
        try:
            category = ErrorCategory(str(mistake.get("category")))
        except ValueError:
            continue
        return {
            "category": category.value,
            "reason": str(mistake.get("reason") or "命中了已审核的典型错误模式"),
            "key_error_step": mistake.get("key_error_step"),
            "suggestion": str(mistake.get("suggestion") or "复习相关概念后重新作答"),
            "confidence": 1.0,
            "source": "reviewed_rule",
            "version": CLASSIFICATION_VERSION,
        }
    return None


def classify_error(snapshot: dict[str, Any], answer: Any, *, correct: bool) -> dict[str, Any] | None:
    if correct:
        return None
    matched = _matched_mistake(snapshot, answer)
    if matched:
        return matched
    if _empty(answer):
        reason, suggestion, confidence = "本题未提交答案，现有证据不足以判断具体错因", "先完成作答，再根据结果定位薄弱环节", 1.0
    else:
        reason, suggestion, confidence = "答案与标准答案不一致，现有作答不足以可靠判断具体错因", "对照解析检查概念、条件、公式和计算过程", 0.2
    return {
        "category": ErrorCategory.UNKNOWN.value,
        "reason": reason,
        "key_error_step": None,
        "suggestion": suggestion,
        "confidence": confidence,
        "source": "deterministic_rule",
        "version": CLASSIFICATION_VERSION,
    }
