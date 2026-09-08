"""Stable request contracts for content operations."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QuestionPatchRequest(BaseModel):
    content: Optional[str] = None
    question_type: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None
    answer: Optional[str] = None
    analysis: Optional[str] = None
    solution_steps: Optional[List[Any]] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    estimated_time: Optional[int] = Field(default=None, ge=1, le=240)
    answer_spec: Optional[Dict[str, Any]] = None
    common_mistakes: Optional[Dict[str, Any]] = None
    variant_blueprint: Optional[Dict[str, Any]] = None
    knowledge_point_codes: Optional[List[str]] = None
    change_reason: Optional[str] = Field(default=None, max_length=1000)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class FeedbackCreateRequest(BaseModel):
    issue_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=5000)


class FeedbackResolveRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=5000)


class LicenseUpdateRequest(BaseModel):
    source_name: Optional[str] = Field(default=None, max_length=255)
    license_type: str = Field(min_length=1, max_length=50)
    license_note: Optional[str] = Field(default=None, max_length=5000)
    license_evidence_ref: Optional[str] = Field(default=None, max_length=500)


class DuplicateDispositionRequest(BaseModel):
    duplicate_of: Optional[str] = Field(default=None, max_length=20)
    is_duplicate: bool
    reason: str = Field(min_length=1, max_length=1000)
