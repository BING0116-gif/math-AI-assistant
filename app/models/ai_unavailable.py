"""
AI 不可用时的统一响应模型。

当 AI 能力不可用时，所有 AI 相关接口返回此结构化响应，
确保前端可识别、用户可理解。
"""

from pydantic import BaseModel
from typing import Optional


class AIUnavailableResponse(BaseModel):
    """AI 功能不可用时的统一响应。"""
    code: str = "AI_UNAVAILABLE"
    message: str
    capability: str
    reason: str

    @classmethod
    def for_capability(cls, capability: str, reason: str) -> "AIUnavailableResponse":
        messages = {
            "chat": "AI 对话功能当前不可用",
            "recognize": "图片识别功能当前不可用",
            "multimodal": "多模态对话功能当前不可用",
            "recommend": "AI 推荐解释功能当前不可用",
            "agent": "AI Agent 功能当前不可用",
        }
        message = messages.get(capability, "AI 功能当前不可用")
        reason_text = {
            "disabled_by_config": "已通过配置关闭 AI 功能",
            "missing_api_key": "未配置 API Key，AI 功能不可用",
        }
        msg = f"{message}（{reason_text.get(reason, reason)}）"
        return cls(
            code="AI_UNAVAILABLE",
            message=msg,
            capability=capability,
            reason=reason,
        )