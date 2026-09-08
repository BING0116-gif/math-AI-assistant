"""Versioned schemas for the Step 3.4 model-quality dataset."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrimaryCategory(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AMBIGUOUS = "ambiguous"
    ADVERSARIAL = "adversarial"
    PLAUSIBLE_WRONG = "plausible_wrong"


class TutorMode(str, Enum):
    HINT_ONLY = "hint_only"
    STEP_BY_STEP = "step_by_step"
    CHECK_MY_WORK = "check_my_work"


class CaseInput(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    image_asset: str | None = None
    image_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    context_fixture: dict[str, Any] = Field(default_factory=dict)
    user_fixture: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def image_fields_are_paired(self) -> "CaseInput":
        if bool(self.image_asset) != bool(self.image_sha256):
            raise ValueError("image_asset and image_sha256 must be provided together")
        return self


class AnswerMatch(StrictModel):
    mode: Literal["exact", "choice", "judge", "numeric", "symbolic", "set", "manual"]
    tolerance: float | None = Field(default=None, ge=0)


class Oracle(StrictModel):
    expected_answer: str
    answer_match: AnswerMatch
    key_steps: list[str] = Field(default_factory=list)
    allowed_expressions: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    knowledge_point_codes: list[str] = Field(min_length=1)
    ambiguity_behavior: str | None = None


class RetrievalExpectation(StrictModel):
    required: bool = False
    expected_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_evidence_ids: list[str] = Field(default_factory=list)
    citation_required: bool = False


class ToolExpectation(StrictModel):
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def tool_sets_do_not_conflict(self) -> "ToolExpectation":
        required, allowed, forbidden = map(
            set, (self.required_tools, self.allowed_tools, self.forbidden_tools)
        )
        if required - allowed:
            raise ValueError("required_tools must be included in allowed_tools")
        if allowed & forbidden:
            raise ValueError("allowed_tools and forbidden_tools must be disjoint")
        return self


class SideEffectExpectation(StrictModel):
    allowed_tables: list[str] = Field(default_factory=list)
    allowed_events: list[str] = Field(default_factory=list)
    forbidden_tables: list[str] = Field(default_factory=list)
    forbidden_events: list[str] = Field(default_factory=list)


class SafetyExpectation(StrictModel):
    must_refuse: bool = False
    protected_canaries: list[str] = Field(default_factory=list)
    prohibited_disclosures: list[str] = Field(default_factory=list)


class GoldReview(StrictModel):
    rationale: str = Field(min_length=5)
    author: str = Field(min_length=3)
    reviewer: str = Field(min_length=3)
    approved_at: datetime

    @model_validator(mode="after")
    def independent_review(self) -> "GoldReview":
        if self.author == self.reviewer:
            raise ValueError("gold author and reviewer must differ")
        return self


DIMENSIONS = {
    "recognition_fidelity",
    "final_correctness",
    "verifiable_reasoning",
    "retrieval_grounding",
    "tool_calls",
    "chinese_latex",
    "safety",
    "cross_user_isolation",
}


class EvaluationCase(StrictModel):
    case_id: str = Field(pattern=r"^mq-[a-z]+-[0-9]{3}$")
    schema_version: Literal["1.0"]
    case_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    status: Literal["draft", "reviewed", "approved"]
    primary_category: PrimaryCategory
    tags: list[str] = Field(default_factory=list)
    modality: Literal["text", "image"]
    tutor_mode: TutorMode
    applicable_dimensions: list[str] = Field(min_length=1)
    ai_offline_case: bool = False
    input: CaseInput
    oracle: Oracle
    retrieval_expectation: RetrievalExpectation
    tool_expectation: ToolExpectation
    side_effect_expectation: SideEffectExpectation
    safety_expectation: SafetyExpectation
    gold: GoldReview

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "EvaluationCase":
        unknown = set(self.applicable_dimensions) - DIMENSIONS
        if unknown:
            raise ValueError(f"unknown scoring dimensions: {sorted(unknown)}")
        if self.modality == "image" and not self.input.image_asset:
            raise ValueError("image cases require an image asset")
        if self.modality == "text" and self.input.image_asset:
            raise ValueError("text cases cannot reference an image asset")
        if self.primary_category == PrimaryCategory.IMAGE and self.modality != "image":
            raise ValueError("image category must use image modality")
        return self


class ManifestCaseRef(StrictModel):
    case_id: str
    path: str


class Manifest(StrictModel):
    schema_version: Literal["1.0"]
    dataset_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str
    course_scope: list[str]
    cases: list[ManifestCaseRef] = Field(min_length=1)
    category_quotas: dict[PrimaryCategory, int]
    tutor_mode_quotas: dict[TutorMode, int]
    minimum_tool_cases: int = Field(ge=0)
    minimum_retrieval_cases: int = Field(ge=0)
    minimum_cross_user_cases: int = Field(ge=0)
    minimum_ai_offline_cases: int = Field(ge=0)


class CaseExecution(StrictModel):
    case_id: str
    attempt: int = Field(ge=1)
    status: Literal["completed", "failed", "not_run"]
    response: str = ""
    model: str | None = None
    prompt_version: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] | None = None
    estimated_cost: float | None = None
    latency_ms: int | None = None
    first_token_latency_ms: int | None = None
    cache_hit: bool | None = None
    retry_count: int = Field(default=0, ge=0)
    event_names: list[str] = Field(default_factory=list)
    side_effects: dict[str, int] = Field(default_factory=dict)
    persistence_evidence: dict[str, Any] = Field(default_factory=dict)
    isolation_ok: bool = True
    error_code: str | None = None


class DimensionResult(StrictModel):
    score: float | None = Field(default=None, ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    needs_human_review: bool = False


class CaseResult(StrictModel):
    case_id: str
    category: PrimaryCategory
    tutor_mode: TutorMode
    execution: CaseExecution
    dimensions: dict[str, DimensionResult]
    weighted_score: float = Field(ge=0, le=100)
    hard_failures: list[str] = Field(default_factory=list)
    root_cause_boundary: str | None = None
    follow_up_test: str | None = None


class RunReport(StrictModel):
    report_schema_version: Literal["1.0"]
    run_id: str
    label: str
    mode: Literal["mocked", "live"]
    status: Literal[
        "mocked_pass",
        "not_run",
        "incomplete",
        "rejected",
        "needs_human_review",
        "baseline_only",
        "approved",
    ]
    reason: str | None = None
    created_at: datetime
    git_sha: str
    dataset_version: str
    dataset_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str
    schema_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    case_hashes: dict[str, str] = Field(default_factory=dict)
    model_provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    safety_filter_version: str | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    full_dataset: bool
    selected_case_ids: list[str]
    summary: dict[str, Any]
    results: list[CaseResult]
    stability_runs: list[CaseResult] = Field(default_factory=list)
    stability_summary: list[dict[str, Any]] = Field(default_factory=list)
    human_review: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None

    @model_validator(mode="after")
    def hashes_cover_selected_cases(self) -> "RunReport":
        invalid = [value for value in self.case_hashes.values() if not re_full_hash(value)]
        if invalid:
            raise ValueError("case_hashes must contain SHA-256 values")
        if self.case_hashes and self.results and set(self.selected_case_ids) - set(self.case_hashes):
            raise ValueError("case_hashes must cover every selected case")
        return self


def re_full_hash(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[a-f0-9]{64}", value))
