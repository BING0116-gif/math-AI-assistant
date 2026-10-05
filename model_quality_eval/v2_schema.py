"""Schema for the next-generation model-quality cases.

The v2 contract is kept separate from the v1 scoring model until the v2
scorer is implemented. This lets v1 remain hash-locked while authors can
validate the richer seven-category case shape early.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class V2StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


V2Category = Literal[
    "basic",
    "advanced_proof",
    "multi_turn",
    "vision",
    "retrieval",
    "tool_failure",
    "security",
]
V2TutorMode = Literal["solve", "hint_only", "step_by_step", "check_my_work"]


class V2KeyStep(V2StrictModel):
    text: str = Field(min_length=1)
    weight: float = Field(default=1, gt=0)


class V2AnswerMatch(V2StrictModel):
    mode: Literal["exact", "numeric", "set", "expression", "behavioral"]
    expected: str | None = None
    tolerance: float | None = Field(default=None, ge=0)


class V2BehavioralRule(V2StrictModel):
    rule: str = Field(min_length=1)
    desc: str = Field(min_length=1)


class V2Oracle(V2StrictModel):
    answer_match: V2AnswerMatch
    key_steps: list[V2KeyStep] = Field(default_factory=list)
    allowed_expressions: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    behavioral_rules: list[V2BehavioralRule] = Field(default_factory=list)


class V2RetrievalExpectation(V2StrictModel):
    required: bool = False
    expected_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_evidence_ids: list[str] = Field(default_factory=list)
    citation_required: bool = False


class V2ToolFailurePlan(V2StrictModel):
    tool: str = Field(min_length=1)
    failure: Literal["timeout", "http_5xx", "unavailable"]
    inject: dict[str, Any] = Field(default_factory=dict)


class V2CriticExpectation(V2StrictModel):
    verdict: Literal["pass", "warn", "fail"]
    must_check: list[
        Literal["answered_question", "derivation_closed", "no_gap", "units_domain", "citations_real", "numeric_consistency", "latex_wellformed"]
    ] = Field(default_factory=list)


class V2Case(V2StrictModel):
    id: str = Field(pattern=r"^mq-v2-[a-z0-9-]+-[0-9]{3}$")
    category: V2Category
    modality: Literal["text", "image"]
    image_asset: str | None = None
    image_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    tutor_mode: V2TutorMode
    question: str = Field(min_length=1, max_length=4000)
    context_fixture: dict[str, Any] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    oracle: V2Oracle
    retrieval_expectation: V2RetrievalExpectation | None = None
    tool_failure_plan: V2ToolFailurePlan | None = None
    critic_expectation: V2CriticExpectation | None = None
    memory_fixture: dict[str, Any] | None = None
    user_fixture: str | dict[str, Any] | None = None
    ai_offline_case: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.category == "vision" and self.modality != "image":
            raise ValueError("vision cases must use image modality")
        if bool(self.image_asset) != bool(self.image_sha256):
            raise ValueError("image_asset and image_sha256 must be provided together")
        if self.category == "vision" and self.modality == "image" and not self.image_asset:
            raise ValueError("vision cases require image_asset and image_sha256")
        if self.category == "tool_failure" and self.tool_failure_plan is None:
            raise ValueError("tool_failure cases require tool_failure_plan")
        if self.category == "retrieval" and self.retrieval_expectation is None:
            raise ValueError("retrieval cases require retrieval_expectation")


class V2ManifestCaseRef(V2StrictModel):
    case_id: str = Field(pattern=r"^mq-v2-[a-z0-9-]+-[0-9]{3}$")
    path: str = Field(min_length=1)


class V2Manifest(V2StrictModel):
    schema_version: Literal["2.0"]
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1)
    cases: list[V2ManifestCaseRef] = Field(min_length=1)
    category_quotas: dict[V2Category, int]


# Explicit aliases make the version boundary discoverable to callers while
# keeping the existing v1 EvaluationCase/Manifest imports unchanged.
EvaluationCaseV2 = V2Case
ManifestV2 = V2Manifest
