"""Trusted Agent tool for requesting a fixed-template teaching animation."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings
from app.services.animation_service import (
    AnimationServiceError,
    animation_job_response,
    enqueue_validated_animation,
    resolve_renderer_digest,
    trusted_animation_visual_spec,
    validate_public_animation_request,
)
from tools.base_tool import BaseTool, ToolCapability, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


class MathAnimateParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: Literal["secant_to_tangent", "riemann_sum"]


class MathAnimateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500, description="动画要帮助学生理解的动态过程")
    parameters: MathAnimateParameters


_EXPLICIT_WORDS = ("动画", "动图", "演示", "过程图", "animate", "animation")
_TEMPLATE_SIGNALS = {
    "secant_to_tangent": ("割线", "切线", "导数", "斜率", "趋近", "极限", "secant", "tangent", "derivative"),
    "riemann_sum": ("黎曼", "积分", "面积", "分割", "矩形", "riemann", "integral", "area"),
}


def animation_teaching_decision(user_input: str, template_id: str, visual_type: str) -> dict[str, Any]:
    """Deterministic guard around the model's tool-selection decision."""
    normalized = " ".join(str(user_input or "").lower().split())
    explicit = any(word in normalized for word in _EXPLICIT_WORDS)
    expected_type = {
        "secant_to_tangent": "tangent_line",
        "riemann_sum": "area_under_curve",
    }.get(template_id)
    concept_match = any(word in normalized for word in _TEMPLATE_SIGNALS.get(template_id, ()))
    admitted = bool(expected_type == visual_type and (explicit or concept_match))
    return {
        "admitted": admitted,
        "trigger": "user_explicit" if explicit else "teaching_strategy",
        "reason": (
            "user explicitly requested a dynamic explanation"
            if explicit and admitted
            else "a changing geometric process materially supports the explanation"
            if admitted
            else "the question does not match an approved high-value dynamic process"
        ),
        "policy_version": "t15-chat-teaching-v1",
    }


class MathAnimateTool(BaseTool):
    name = "math_animate"
    description = (
        "在当前数学对话中创建教学动画，并由聊天消息内嵌展示。仅当动态变化明显比静态图或文字更直观时调用，"
        "或用户明确要求动画时调用；普通计算、方程求解、静态关系不要调用。当前只支持两个可信模板："
        "secant_to_tangent（仅 y=x^2 在 x=1 处割线趋近切线，spec.type=tangent_line）和 "
        "riemann_sum（仅 y=x^2 在 [0,2] 上黎曼和趋近积分，spec.type=area_under_curve）。"
        "模型只选择 template_id，不提交坐标、公式或代码；数学数据由服务端可信模板提供。调用动画后，回答中仍须配套解释"
        "画面每一步说明的数学含义；不要把动画当成答案本身。"
    )
    version = "1.0.0"
    capabilities = [ToolCapability.PLOTTING]
    args_schema = MathAnimateArgs

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": self.args_schema.model_json_schema(),
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        if not settings.MATH_ANIMATION_ENABLED:
            return self._fallback("动画能力当前未启用，请继续使用文字和静态图讲解")

        params = input_data.parameters.get("parameters", input_data.parameters)
        if isinstance(params, BaseModel):
            params = params.model_dump(exclude_none=True)
        parsed = MathAnimateParameters.model_validate(params)
        visual_type = {
            "secant_to_tangent": "tangent_line",
            "riemann_sum": "area_under_curve",
        }[parsed.template_id]
        decision = animation_teaching_decision(
            str(input_data.context.get("original_user_input") or ""),
            parsed.template_id,
            visual_type,
        )
        if not decision["admitted"]:
            return self._fallback("动画准入未通过，请用文字或静态图继续讲解", decision)

        user_id = str(input_data.context.get("user_id") or "")
        session_id = str(input_data.context.get("session_id") or "")
        if not user_id or not session_id:
            return ToolOutput(success=False, error="缺少可信会话身份", tool_name=self.name)

        try:
            raw_spec = trusted_animation_visual_spec(parsed.template_id)
            admission, source_hash = validate_public_animation_request(
                template_id=parsed.template_id,
                visual_spec=raw_spec,
            )
            admission.update(decision)
            canonical = json.dumps(raw_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            key_hash = hashlib.sha256(f"{session_id}\n{parsed.template_id}\n{canonical}".encode()).hexdigest()
            from app.data.database import get_db_session

            async with get_db_session() as db:
                job = await enqueue_validated_animation(
                    db,
                    user_id=user_id,
                    idempotency_key=f"chat:{key_hash}",
                    template_id=parsed.template_id,
                    trigger=decision["trigger"],
                    visual_spec=raw_spec,
                    admission_snapshot=admission,
                    template_source_sha256=source_hash,
                    renderer_image_digest=resolve_renderer_digest(),
                    policy_version=decision["policy_version"],
                )
                await db.refresh(job, attribute_names=["artifacts"])
                payload = animation_job_response(job).model_dump(mode="json")
            payload["teaching_note"] = raw_spec["teaching_note"]
            sink = input_data.context.get("animations")
            if isinstance(sink, list) and not any(item.get("job_id") == payload["job_id"] for item in sink):
                sink.append(payload)
            return ToolOutput(
                success=True,
                result="动画任务已加入当前对话。请继续给出与动画步骤同步的数学讲解。",
                data=payload,
                tool_name=self.name,
                metadata={"status": payload["status"], "template_id": parsed.template_id},
            )
        except (AnimationServiceError, KeyError, ValueError) as exc:
            logger.warning("MathAnimator tool rejected request: %s", str(exc)[:240])
            return self._fallback("动画规格未通过校验，请继续使用文字和静态图讲解", decision)

    def _fallback(self, message: str, decision: dict[str, Any] | None = None) -> ToolOutput:
        payload = {"animation_status": "static_fallback", "message": message}
        if decision:
            payload["decision"] = decision
        return ToolOutput(success=True, result=json.dumps(payload, ensure_ascii=False), data=payload, tool_name=self.name)
