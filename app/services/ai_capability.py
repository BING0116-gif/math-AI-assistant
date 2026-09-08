"""
AI 能力状态管理 — 统一表达 AI 是否可用。

遵循设计：
- AI_ENABLED 配置开关（默认 true 保持兼容）
- 最终可用性: AI_ENABLED == true AND (LLM_API_KEY 或 DASHSCOPE_API_KEY) 非空
- 提供明确状态对象，供业务代码查询
- 不使用到处判断 None 的设计
"""

from enum import Enum
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel
from app.config.settings import settings


class AIUnavailableReason(str, Enum):
    """AI 不可用原因。"""
    DISABLED_BY_CONFIG = "disabled_by_config"
    MISSING_API_KEY = "missing_api_key"


class AICapabilityState(BaseModel):
    """AI 能力统一状态。"""
    enabled_config: bool
    """AI_ENABLED 配置是否为 true。"""

    has_api_key: bool
    """文本 LLM 密钥（LLM_API_KEY，兜底 DASHSCOPE_API_KEY）是否非空。"""

    available: bool
    """AI 是否实际可用。"""

    reason: Literal["enabled", "disabled_by_config", "missing_api_key"]
    """不可用时的原因。"""

    @classmethod
    def compute(cls) -> "AICapabilityState":
        """从当前配置计算状态。"""
        enabled_config = getattr(settings, "AI_ENABLED", True)
        # 文本 LLM 密钥：优先 LLM_API_KEY，兜底 DASHSCOPE_API_KEY。
        # 视觉链路（vision_tool / qwen-vl-plus）仍只读 DASHSCOPE_API_KEY，互不影响。
        _text_key = (settings.LLM_API_KEY or settings.DASHSCOPE_API_KEY) or ""
        has_api_key = bool(_text_key and _text_key.strip())
        available = enabled_config and has_api_key

        if available:
            reason = "enabled"
        elif not enabled_config:
            reason = "disabled_by_config"
        else:
            reason = "missing_api_key"

        return cls(
            enabled_config=enabled_config,
            has_api_key=has_api_key,
            available=available,
            reason=reason,
        )


# 单例全局状态，在应用启动时计算
_ai_capability_state: AICapabilityState | None = None


def get_ai_capability() -> AICapabilityState:
    """获取当前 AI 能力状态。"""
    global _ai_capability_state
    if _ai_capability_state is None:
        _ai_capability_state = AICapabilityState.compute()
    return _ai_capability_state


def is_ai_available() -> bool:
    """快捷判断 AI 是否可用。"""
    return get_ai_capability().available


def reset_for_test() -> None:
    """重置状态（用于测试）。"""
    global _ai_capability_state
    _ai_capability_state = None


def raise_ai_unavailable(capability: str) -> None:
    """抛出一个机器可识别的 AI 不可用 503 异常。

    所有 AI-dependent endpoint 应使用此函数，确保返回统一契约。
    """
    from app.models.ai_unavailable import AIUnavailableResponse

    cap = get_ai_capability()
    resp = AIUnavailableResponse.for_capability(capability, cap.reason)
    raise HTTPException(
        status_code=503,
        detail=resp.model_dump(),
    )
