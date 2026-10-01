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
