"""L4 安全降级文案（路线图 4.4.1）。

prompts/degradation.yaml 是模板的唯一事实源；加载失败时使用同文案硬编码兜底，
保证任何故障场景下都能给出诚实、可行动的降级回答，绝不假装成功。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK_TEMPLATES = {
    "model_failure": (
        "**【服务暂不可用】** AI 服务暂时不可用（已自动切换仍失败）。你的问题已保存，"
        "稍后点击重试即可，不会丢失上下文。"
    ),
    "timeout": (
        "**【⏰ 执行超时】** 这道题的推导超时了，已保留目前的过程。"
        "建议：把问题拆小一点再问，或稍后重试。"
    ),
    "tool_unavailable": (
        "**【功能暂不可用】** 该功能暂时不可用，我先用文字方式帮你。"
        "你可以把题目条件打出来。"
    ),
}

_CACHE: dict[str, str] | None = None


def _load_templates() -> dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    templates = dict(_FALLBACK_TEMPLATES)
    try:
        import yaml

        path = Path(__file__).resolve().parent.parent / "prompts" / "degradation.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, text in (data.get("templates") or {}).items():
            if isinstance(name, str) and isinstance(text, str) and text.strip():
                templates[name] = text.strip()
    except Exception as exc:
        logger.warning(f"[DEGRADATION] 降级文案加载失败，使用内置兜底模板: {exc}")
    _CACHE = templates
    return _CACHE


def degradation_text(name: str) -> str:
    """Return the honest degradation copy for a failure class (never fabricates success)."""
    return _load_templates().get(name) or _FALLBACK_TEMPLATES.get(name, "AI 服务暂时不可用，请稍后重试。")
