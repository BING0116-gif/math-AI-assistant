"""Strict public contracts for the disabled-by-default MathAnimator API."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PublicTemplateId = Literal["secant_to_tangent", "riemann_sum"]
AnimationStatus = Literal["pending", "running", "succeeded", "fallback", "failed", "cancelled"]


class CreateAnimationJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    template_id: PublicTemplateId
    trigger: Literal["user_explicit"] = "user_explicit"
    visual_spec: dict[str, Any]

    @field_validator("visual_spec")
    @classmethod
    def bound_visual_spec(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if not value or len(encoded.encode("utf-8")) > 50_000:
            raise ValueError("visual_spec 不能为空且不得超过 50000 字节")
        return value


class AnimationArtifactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["video", "thumbnail", "gif"]
    mime_type: str
    size_bytes: int = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)


class AnimationJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    job_id: str
    status: AnimationStatus
    stage: str
    template_id: str
    attempt_count: int = Field(ge=0, le=2)
    fallback_kind: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: list[AnimationArtifactSummary] = Field(default_factory=list)
