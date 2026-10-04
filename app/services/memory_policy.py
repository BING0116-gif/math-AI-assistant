"""Pure lifecycle and summary policy for persisted learner memories."""

from __future__ import annotations

from typing import Any, Dict, Optional

MEMORY_TYPE_ERROR = "error"
MEMORY_TYPE_CONVERSATION = "conversation"
MEMORY_TYPE_MILESTONE = "milestone"
MEMORY_TYPE_PROFILE = "profile"

STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"

MEMORY_INIT_STRENGTH = {
    MEMORY_TYPE_ERROR: 0.70,
    MEMORY_TYPE_CONVERSATION: 0.60,
    MEMORY_TYPE_MILESTONE: 0.85,
    MEMORY_TYPE_PROFILE: 1.0,
}

MEMORY_TTL = {
    MEMORY_TYPE_ERROR: 2 * 365 * 86400,
    MEMORY_TYPE_CONVERSATION: 180 * 86400,
    MEMORY_TYPE_MILESTONE: 100 * 365 * 86400,
    MEMORY_TYPE_PROFILE: 30 * 86400,
}

DECAY_LAMBDA = {
    MEMORY_TYPE_ERROR: 0.0045,
    MEMORY_TYPE_CONVERSATION: 0.0045,
    MEMORY_TYPE_MILESTONE: 0.0015,
    MEMORY_TYPE_PROFILE: 0.0,
}

# ── 阶段四 6.1/6.3:防污染类型系统与置信度 ──────────────────────────────
# kind 隔离三条污染防线:preference ≠ 数学事实;misconception 注入必须带纠正框架;
# context 带时间标注。无 kind 不落库(写入路径强制推断)。
MEMORY_KIND_PREFERENCE = "preference"
MEMORY_KIND_FACT = "fact"
MEMORY_KIND_MISCONCEPTION = "misconception"
MEMORY_KIND_CONTEXT = "context"

MEMORY_KINDS = frozenset({MEMORY_KIND_PREFERENCE, MEMORY_KIND_FACT, MEMORY_KIND_MISCONCEPTION, MEMORY_KIND_CONTEXT})

# memory_type → kind 启发式:错题复盘=misconception,画像/里程碑=fact,对话=context。
KIND_BY_MEMORY_TYPE = {
    MEMORY_TYPE_ERROR: MEMORY_KIND_MISCONCEPTION,
    MEMORY_TYPE_PROFILE: MEMORY_KIND_FACT,
    MEMORY_TYPE_MILESTONE: MEMORY_KIND_FACT,
    MEMORY_TYPE_CONVERSATION: MEMORY_KIND_CONTEXT,
}

CONFIDENCE_AUTO_EXTRACTED = 0.5
CONFIDENCE_USER_CONFIRMED = 0.9
CONFIDENCE_USER_CORRECTED = 0.95
CONFIDENCE_REOBSERVED_BONUS = 0.1
CONFIDENCE_CAP = 0.95
CONFIDENCE_CONTRADICTION_PENALTY = 0.2
# 归档联动:confidence × memory_strength 低于阈值 → archive(6.3)
CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD = 0.15


def infer_memory_kind(memory_type: str, explicit_kind: Optional[str] = None) -> str:
    """写入路径强制 kind:显式指定优先(校验合法),否则按 memory_type 启发式。"""
    if explicit_kind is not None:
        if explicit_kind not in MEMORY_KINDS:
            raise ValueError(f"unknown memory kind: {explicit_kind}")
        return explicit_kind
    return KIND_BY_MEMORY_TYPE.get(memory_type, MEMORY_KIND_CONTEXT)


# 6.6 对话记忆 kind 细分:风格/偏好表述 → preference(影响"怎么讲"),
# 课程/进度陈述 → fact(影响"讲什么、从哪讲起"),其余 → context。
_STYLE_PREFERENCE_KEYWORDS = (
    "分步讲解", "先讲思路", "不要直接给答案", "多举例子", "打个比方",
    "慢一点", "快一点", "简短一点", "详细一点", "节奏", "符号习惯",
    "讲解风格", "喜欢怎么讲", "希望你怎么讲",
)
_PROGRESS_KEYWORDS = (
    "已完成", "已学完", "学过了", "没学过", "还没学", "正在学", "正在备考",
    "复习到", "学完", "上册", "下册", "课程进度",
)


def infer_conversation_kind(content: str) -> str:
    """对话记忆的确定性 kind 分类(6.6);仅风格/偏好与进度陈述离义,其余保守 context。"""
    text = (content or "")[:200]
    if any(keyword in text for keyword in _STYLE_PREFERENCE_KEYWORDS):
        return MEMORY_KIND_PREFERENCE
    if any(keyword in text for keyword in _PROGRESS_KEYWORDS):
        return MEMORY_KIND_FACT
    return MEMORY_KIND_CONTEXT

_SUMMARY_RULES = {
    MEMORY_TYPE_ERROR: ("错题", 150),
    MEMORY_TYPE_CONVERSATION: ("对话", 120),
    MEMORY_TYPE_MILESTONE: ("里程碑", 80),
    MEMORY_TYPE_PROFILE: ("画像", 50),
}


def build_embedding_summary(
    content: str,
    memory_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the deterministic text used for vector embedding.

    ``metadata`` remains accepted for compatibility and future policy versions;
    current summaries intentionally depend only on persisted content and type.
    """
    del metadata
    rule = _SUMMARY_RULES.get(memory_type)
    if rule is None:
        return content[:150]
    label, limit = rule
    return f"{label}: {content[:limit]}"


__all__ = [
    "DECAY_LAMBDA",
    "MEMORY_INIT_STRENGTH",
    "MEMORY_TTL",
    "MEMORY_TYPE_CONVERSATION",
    "MEMORY_TYPE_ERROR",
    "MEMORY_TYPE_MILESTONE",
    "MEMORY_TYPE_PROFILE",
    "STATUS_ACTIVE",
    "STATUS_ARCHIVED",
    "STATUS_DELETED",
    "STATUS_PENDING",
    "build_embedding_summary",
]
