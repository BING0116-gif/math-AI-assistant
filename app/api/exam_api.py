"""Authenticated autonomous exam API."""
from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.exam_service import create_exam, exam_ai_summary, exam_options, exam_report, get_exam, save_exam_draft, start_exam, submit_exam
from app.services.practice_service import PracticeError

router = APIRouter(prefix="/api/exams", tags=["自主考试"])
QuestionType = Literal["choice", "judge", "numeric_fill", "expression_fill"]


class CreateExamRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    chapter_ids: list[str] = Field(default_factory=list, max_length=30)
    knowledge_point_codes: list[str] = Field(default_factory=list, max_length=100)
    difficulty_min: int = Field(ge=1, le=5)
    difficulty_max: int = Field(ge=1, le=5)
    question_type_counts: dict[QuestionType, int]
    duration_minutes: Literal[30, 45, 60, 90]
    idempotency_key: str = Field(min_length=8, max_length=128)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)

    @field_validator("chapter_ids", "knowledge_point_codes")
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)): raise ValueError("不允许重复选择")
        return value

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.chapter_ids and not self.knowledge_point_codes: raise ValueError("至少选择一个章节或知识点")
        if self.difficulty_min > self.difficulty_max: raise ValueError("难度范围不合法")
        total = sum(self.question_type_counts.values())
        if any(value < 0 or value > 30 for value in self.question_type_counts.values()) or not 5 <= total <= 30: raise ValueError("各题型数量之和必须在 5 到 30 之间")
        return self


class DraftRequest(BaseModel):
    answer: Any = None
    expected_version: int = Field(ge=0)


class SubmitRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


def _user(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(user_id)


def _raise(error: PracticeError):
    status = 404 if error.code == "SESSION_NOT_FOUND" else 409 if error.code in {"SESSION_STATE_CONFLICT", "IDEMPOTENCY_CONFLICT"} else 503 if error.code in {"AI_UNAVAILABLE", "AI_SUMMARY_FAILED"} else 422
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message, **error.extra})


@router.get("/options")
async def options(course_id: str | None = Query(default=None, max_length=36)):
    try: return {"code": 0, "data": await exam_options(course_id)}
    except PracticeError as error: _raise(error)


@router.post("/sessions")
async def create(request: Request, body: CreateExamRequest):
    try: return {"code": 0, "data": await create_exam(_user(request), body.model_dump(exclude_none=True))}
    except PracticeError as error: _raise(error)


@router.get("/sessions/{session_id}")
async def get(request: Request, session_id: str):
    try: return {"code": 0, "data": await get_exam(_user(request), session_id)}
    except PracticeError as error: _raise(error)


@router.post("/sessions/{session_id}/start")
async def start(request: Request, session_id: str):
    try: return {"code": 0, "data": await start_exam(_user(request), session_id)}
    except PracticeError as error: _raise(error)


@router.put("/sessions/{session_id}/draft-answers/{question_id}")
async def draft(request: Request, session_id: str, question_id: str, body: DraftRequest):
    try: return {"code": 0, "data": await save_exam_draft(_user(request), session_id, question_id, body.answer, body.expected_version)}
    except PracticeError as error: _raise(error)


@router.post("/sessions/{session_id}/submit")
async def submit(request: Request, session_id: str, body: SubmitRequest):
    try: return {"code": 0, "data": await submit_exam(_user(request), session_id)}
    except PracticeError as error: _raise(error)


@router.get("/sessions/{session_id}/report")
async def report(request: Request, session_id: str):
    try: return {"code": 0, "data": await exam_report(_user(request), session_id)}
    except PracticeError as error: _raise(error)


@router.post("/sessions/{session_id}/report/ai-summary")
async def ai_summary(request: Request, session_id: str):
    try: return {"code": 0, "data": await exam_ai_summary(_user(request), session_id)}
    except PracticeError as error: _raise(error)
