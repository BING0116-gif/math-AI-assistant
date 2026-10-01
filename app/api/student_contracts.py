"""Shared OpenAPI contracts for authenticated student learning flows.

The services behind practice, assessment, and exams intentionally return dicts so
they can share their transactional implementation.  These models make the public
shape explicit without changing the existing JSON payloads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str | None = None
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail | str


STUDENT_API_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "The resource belongs to another user"},
    404: {"model": ErrorResponse, "description": "The owned resource does not exist"},
    422: {"model": ErrorResponse, "description": "Request or domain validation failed"},
    503: {"model": ErrorResponse, "description": "A required dependency is unavailable"},
}


class StudentQuestion(BaseModel):
    """Question fields exposed to a student; grading secrets are never declared."""

    model_config = ConfigDict(extra="allow")

    question_id: str
    content: str | None = None
    question_type: str | None = None
    options: list[Any] | None = None
    difficulty: int | None = None
    draft_answer: Any = None
    draft_version: int | None = None


class StudentSession(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    status: str | None = None
    mode: str | None = None
    questions: list[StudentQuestion] = Field(default_factory=list)
    config: dict[str, Any] | None = None
    recovery_snapshot: dict[str, Any] | None = None
    created_at: datetime | str | None = None
    started_at: datetime | str | None = None
    completed_at: datetime | str | None = None


class StudentOperation(BaseModel):
    """Stable superset used by the student session endpoints.

    Fields read by first-party clients are explicit. ``extra=allow`` preserves
    legacy fields during the documented compatibility window.
    """

    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    status: str | None = None
    questions: list[StudentQuestion] | None = None
    config: dict[str, Any] | None = None
    recovery_snapshot: dict[str, Any] | None = None
    question_id: str | None = None
    # Attempt responses expose a boolean, while completed-session reports expose
    # the aggregate number of correct answers under the same legacy field name.
    correct: bool | int | None = None
    retry_count: int | None = None
    draft_version: int | None = None
    score: float | None = None
    total: int | None = None
    summary: str | None = None
    cached: bool | None = None
    courses: list[dict[str, Any]] | None = None
    chapters: list[dict[str, Any]] | None = None
    knowledge_points: list[dict[str, Any]] | None = None
    question_types: list[dict[str, Any]] | None = None


T = TypeVar("T")


class StudentEnvelope(BaseModel, Generic[T]):
    code: Literal[0] = 0
    data: T
    message: str | None = None


StudentOperationEnvelope = StudentEnvelope[StudentOperation | list[StudentOperation]]


class SuccessResponse(BaseModel):
    success: bool


class ErrorBookItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    question: str
    question_type: str = "text"
    image_path: str | None = None
    error_reason: str = ""
    categories: list[str] = Field(default_factory=list)
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3
    is_mastered: bool = False


class ErrorBookCreateResponse(BaseModel):
    id: str
    status: Literal["success"]
    message: str
    data: ErrorBookItem


class ErrorReviewResponse(BaseModel):
    id: str
    review_state: str
    is_mastered: bool
    last_reviewed_at: datetime | None = None


class MasteryEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    mastery: float
    attempts: int
    correct: int
    status: Literal["untouched", "weak", "learning", "mastered"]


class MasteryResponse(BaseModel):
    mastery: dict[str, MasteryEvidence]


class CourseSummary(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    subject: str


class VersionSummary(BaseModel):
    id: str
    version: str
    name: str
    status: str


class KnowledgePointSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    code: str
    name: str
    description: str | None = None
    difficulty: int
    importance: float
    sort_order: int
    prerequisites: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class ChapterSummary(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    sort_order: int
    level: int
    children: list["ChapterSummary"] = Field(default_factory=list)
    knowledge_points: list[KnowledgePointSummary] = Field(default_factory=list)


class CourseListResponse(BaseModel):
    courses: list[CourseSummary]


class CourseTreeResponse(BaseModel):
    course: CourseSummary
    version: VersionSummary
    chapters: list[ChapterSummary]


class KnowledgeSearchResponse(BaseModel):
    course_id: str
    version: VersionSummary
    query: str
    results: list[KnowledgePointSummary]


class KnowledgePointResponse(KnowledgePointSummary):
    model_config = ConfigDict(extra="allow")

    course: CourseSummary
    version: VersionSummary
    aliases: list[str] = Field(default_factory=list)
    learning_objectives: list[Any] = Field(default_factory=list)
    common_errors: list[Any] = Field(default_factory=list)
    key_concepts: list[Any] = Field(default_factory=list)
    key_formulas: list[Any] = Field(default_factory=list)
    exam_focuses: list[Any] = Field(default_factory=list)
    resources: list[dict[str, Any]] | None = None
    prerequisite_points: list[dict[str, str]] | None = None


class ChatMessageResponse(BaseModel):
    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    status: str
    default_tutor_mode: str
    context: dict[str, Any] = Field(default_factory=dict)
    message_count: int | None = None
    messages: list[ChatMessageResponse] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


ChatSessionEnvelope = StudentEnvelope[ChatSessionResponse]
ChatSessionListEnvelope = StudentEnvelope[list[ChatSessionResponse]]


class RecommendationData(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = None
    question_count: int | None = None
    category: str | None = None
    recommended_difficulty: int | float | str | None = None
    questions: list[dict[str, Any]] | None = None
    ai_analysis: Any = None
    meta: dict[str, Any] | None = None
    user_id: str | None = None
    weak_points: list[Any] | None = None
    strong_points: list[Any] | None = None
    results: list[dict[str, Any]] | None = None


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    data: RecommendationData | None
    request_id: str | None = None
    generated_at: datetime | str | None = None
    processing_time_ms: float | None = None
    errors: list[Any] | None = None
