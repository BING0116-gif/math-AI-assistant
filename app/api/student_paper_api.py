"""Authenticated student paper composition API."""
from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.student_contracts import STUDENT_API_RESPONSES
from app.services.practice_service import PracticeError
from app.services.student_paper_service import (
    add_question, create_paper, finalize_paper, get_paper, launch_paper,
    list_papers, remove_question, reorder_questions, replace_question, update_paper,
)

router = APIRouter(prefix="/api/student-papers", tags=["学生组卷"])


class CreatePaperRequest(BaseModel):
    title: str = Field(default="未命名试卷", min_length=1, max_length=200)
    course_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    source_type: Literal["manual", "ai", "recommended"] = "manual"
    question_ids: list[str] = Field(default_factory=list, max_length=50)
    blueprint_buckets: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    blueprint_snapshot: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    default_score: float = Field(default=1, gt=0, le=100)


class UpdatePaperRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["draft", "ready", "archived"] | None = None


class AddQuestionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=20)
    score: float = Field(default=1, gt=0, le=100)


class ReorderRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=50)
    expected_revision: int = Field(ge=1)


class FinalizeRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class LaunchRequest(BaseModel):
    mode: Literal["practice", "test"]
    behavior: Literal["immediate", "adaptive", "deferred"] = "adaptive"
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    idempotency_key: str = Field(min_length=8, max_length=128)


def _user(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(user_id)


def _raise(error: PracticeError):
    if error.code in {"PAPER_NOT_FOUND", "QUESTION_NOT_FOUND"}:
        status = 404
    elif error.code in {"REVISION_CONFLICT", "PAPER_STATE_CONFLICT", "IDEMPOTENCY_CONFLICT", "QUESTION_ALREADY_EXISTS"}:
        status = 409
    else:
        status = 422
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message, **error.extra})


@router.get("", responses=STUDENT_API_RESPONSES)
async def get_papers(request: Request, limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    return {"code": 0, "data": await list_papers(_user(request), limit=limit, offset=offset)}


@router.post("", responses=STUDENT_API_RESPONSES)
async def post_paper(request: Request, body: CreatePaperRequest):
    try: return {"code": 0, "data": await create_paper(_user(request), body.model_dump(exclude_none=True))}
    except PracticeError as error: _raise(error)


@router.get("/{paper_id}", responses=STUDENT_API_RESPONSES)
async def get_paper_detail(request: Request, paper_id: str):
    try: return {"code": 0, "data": await get_paper(_user(request), paper_id)}
    except PracticeError as error: _raise(error)


@router.patch("/{paper_id}", responses=STUDENT_API_RESPONSES)
async def patch_paper(request: Request, paper_id: str, body: UpdatePaperRequest):
    try: return {"code": 0, "data": await update_paper(_user(request), paper_id, body.model_dump(exclude_none=True))}
    except PracticeError as error: _raise(error)


@router.post("/{paper_id}/questions", responses=STUDENT_API_RESPONSES)
async def post_question(request: Request, paper_id: str, body: AddQuestionRequest):
    try: return {"code": 0, "data": await add_question(_user(request), paper_id, body.question_id, body.score)}
    except PracticeError as error: _raise(error)


@router.post("/{paper_id}/questions/{item_id}/replace", responses=STUDENT_API_RESPONSES)
async def post_replace(request: Request, paper_id: str, item_id: str):
    try: return {"code": 0, "data": await replace_question(_user(request), paper_id, item_id)}
    except PracticeError as error: _raise(error)


@router.delete("/{paper_id}/questions/{item_id}", responses=STUDENT_API_RESPONSES)
async def delete_question(request: Request, paper_id: str, item_id: str):
    try: return {"code": 0, "data": await remove_question(_user(request), paper_id, item_id)}
    except PracticeError as error: _raise(error)


@router.put("/{paper_id}/question-order", responses=STUDENT_API_RESPONSES)
async def put_order(request: Request, paper_id: str, body: ReorderRequest):
    try: return {"code": 0, "data": await reorder_questions(_user(request), paper_id, body.item_ids, body.expected_revision)}
    except PracticeError as error: _raise(error)


@router.post("/{paper_id}/finalize", responses=STUDENT_API_RESPONSES)
async def post_finalize(request: Request, paper_id: str, body: FinalizeRequest):
    try: return {"code": 0, "data": await finalize_paper(_user(request), paper_id, body.expected_revision)}
    except PracticeError as error: _raise(error)


@router.post("/{paper_id}/launch", responses=STUDENT_API_RESPONSES)
async def post_launch(request: Request, paper_id: str, body: LaunchRequest):
    try: return {"code": 0, "data": await launch_paper(_user(request), paper_id, body.model_dump(exclude_none=True))}
    except PracticeError as error: _raise(error)
