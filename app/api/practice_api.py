"""Student-facing specialist practice API.

Unlike the legacy paper demo, every resource lookup is scoped to the authenticated
owner and every request is explicitly validated by Pydantic.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.practice_service import (
    PracticeError, complete_session, create_error_book_session, create_session, get_session,
    practice_options, recent_sessions, result, save_practice_snapshot, start_session, submit_attempt,
)

router = APIRouter(prefix="/api/practice", tags=["专项练习"])


class CreatePracticeSessionRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    chapter_ids: list[str] = Field(default_factory=list, max_length=30)
    knowledge_point_codes: list[str] = Field(default_factory=list, max_length=100)
    difficulty_band: tuple[int, int] | None = None
    question_types: list[Literal["choice", "multi_choice", "judge", "numeric_fill", "expression_fill"]] = Field(default_factory=list)
    question_count: int = Field(ge=5, le=20)
    idempotency_key: str = Field(min_length=8, max_length=128)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    review_schedule_id: int | None = Field(default=None, ge=1)
    review_kind: Literal["original_correct", "variant_correct", "spaced_correct"] | None = None
    # ---- §5.1 答题行为与排序（默认值等价旧行为，向后兼容）----
    behavior: Literal["immediate", "adaptive", "deferred"] = Field(default="immediate")
    order_mode: Literal["sequential", "random"] = Field(default="random")
    # §5.4 选项乱序（练习默认关闭，考试场景语义默认开）
    shuffle_options: bool = False

    @field_validator("chapter_ids", "knowledge_point_codes", "question_types")
    @classmethod
    def no_duplicates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("不允许重复选择")
        return value

    @model_validator(mode="after")
    def validate_scope_and_difficulty(self):
        if not self.chapter_ids and not self.knowledge_point_codes:
            raise ValueError("至少选择一个章节或知识点")
        if self.difficulty_band and self.difficulty_band[0] > self.difficulty_band[1]:
            raise ValueError("难度范围不合法")
        if self.difficulty_band and not (1 <= self.difficulty_band[0] <= 5 and 1 <= self.difficulty_band[1] <= 5):
            raise ValueError("难度必须在 1 到 5 之间")
        if bool(self.review_schedule_id) != bool(self.review_kind):
            raise ValueError("复习排期和复习类型必须同时提供")
        return self


class SubmitPracticeAttemptRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    answer: Any = None
    idempotency_key: str = Field(min_length=8, max_length=128)
    time_spent_seconds: int | None = Field(default=None, ge=0, le=86400)
    hint_used: bool = False
    solution_viewed: bool = False


class CreateFromErrorBookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str | None = Field(default=None, min_length=1, max_length=36)
    version_id: str | None = Field(default=None, min_length=1, max_length=36)
    behavior: Literal["immediate", "adaptive", "deferred"] = Field(default="immediate")
    order_mode: Literal["sequential", "random"] = Field(default="sequential")
    question_limit: int = Field(default=20, ge=1, le=50)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class RecoverySnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_question_id: str | None = Field(default=None, max_length=36)


def _user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(user_id)


def _raise(error: PracticeError) -> None:
    status = 404 if error.code == "SESSION_NOT_FOUND" else 409 if error.code in {"SESSION_STATE_CONFLICT", "ANSWER_ALREADY_COMMITTED", "IDEMPOTENCY_CONFLICT"} else 422 if error.code in {"VALIDATION_FAILED", "INSUFFICIENT_QUESTION_POOL", "COURSE_VERSION_NOT_AVAILABLE"} else 400
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message, **error.extra})


@router.get("/options")
async def get_options(course_id: str | None = Query(default=None, max_length=36)):
    try:
        return {"code": 0, "data": await practice_options(course_id)}
    except PracticeError as error:
        _raise(error)


@router.get("/sessions")
async def get_recent_sessions(request: Request, limit: int = Query(default=8, ge=1, le=20)):
    return {"code": 0, "data": await recent_sessions(_user_id(request), limit)}


@router.post("/sessions")
async def post_session(request: Request, body: CreatePracticeSessionRequest):
    try:
        return {"code": 0, "data": await create_session(_user_id(request), body.model_dump(exclude_none=True))}
    except PracticeError as error:
        _raise(error)


@router.post("/sessions/from-error-book")
async def post_session_from_error_book(request: Request, body: CreateFromErrorBookRequest):
    try:
        return {"code": 0, "data": await create_error_book_session(
            _user_id(request),
            course_id=body.course_id, version_id=body.version_id,
            behavior=body.behavior, order_mode=body.order_mode,
            question_limit=body.question_limit, random_seed=body.random_seed,
            idempotency_key=body.idempotency_key,
        )}
    except PracticeError as error:
        _raise(error)


@router.put("/sessions/{session_id}/recovery-snapshot")
async def put_recovery_snapshot(request: Request, session_id: str, body: RecoverySnapshotRequest):
    try:
        return {"code": 0, "data": await save_practice_snapshot(_user_id(request), session_id, body.current_question_id), "message": "ok"}
    except PracticeError as error:
        _raise(error)


@router.get("/sessions/{session_id}")
async def get_practice_session(request: Request, session_id: str):
    try:
        return {"code": 0, "data": await get_session(_user_id(request), session_id)}
    except PracticeError as error:
        _raise(error)


@router.post("/sessions/{session_id}/start")
async def post_start(request: Request, session_id: str):
    try:
        return {"code": 0, "data": await start_session(_user_id(request), session_id)}
    except PracticeError as error:
        _raise(error)


@router.post("/sessions/{session_id}/attempts")
async def post_attempt(request: Request, session_id: str, body: SubmitPracticeAttemptRequest):
    try:
        signals = body.model_dump(include={"time_spent_seconds", "hint_used", "solution_viewed"}, exclude_none=True)
        return {"code": 0, "data": await submit_attempt(_user_id(request), session_id, body.question_id, body.answer, body.idempotency_key, signals)}
    except PracticeError as error:
        _raise(error)


@router.post("/sessions/{session_id}/complete")
async def post_complete(request: Request, session_id: str):
    try:
        return {"code": 0, "data": await complete_session(_user_id(request), session_id)}
    except PracticeError as error:
        _raise(error)


@router.get("/sessions/{session_id}/result")
async def get_result(request: Request, session_id: str):
    try:
        return {"code": 0, "data": await result(_user_id(request), session_id)}
    except PracticeError as error:
        _raise(error)
