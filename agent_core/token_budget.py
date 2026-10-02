"""Small, dependency-optional token estimation helpers for Agent budgets.

The provider-reported usage remains authoritative. This module is only used
before a request is sent, so deployments without tiktoken still get a
conservative estimate instead of an unbounded context.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=4)
def _encoder(model: str):
    try:
        import tiktoken  # optional dependency
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def estimate_tokens(text: str, model: str = "") -> int:
    value = str(text or "")
    if not value:
        return 0
    encoder = _encoder(model or "default")
    if encoder is not None:
        try:
            return len(encoder.encode(value, disallowed_special=()))
        except Exception:
            pass
    # Conservative mixed Chinese/Latin fallback: CJK is usually close to one
    # token per character; Latin text averages about four characters/token.
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in value)
    non_cjk = len(value) - cjk
    return max(1, cjk + (non_cjk + 3) // 4)
