from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.learning_activity import ActivityError, end_activity, heartbeat_activity, start_activity
from app.services.learning_hub import LearningHubError, complete_review, defer_review, due_reviews, today_hub, unified_dashboard, unified_profile

router = APIRouter(prefix="/api/learning", tags=["学习闭环"])

class ReviewItem(BaseModel):
    id: int
    knowledge_point_code: str
    knowledge_point_name: str
    due_at: datetime
    interval_days: int
    review_count: int
    stage: int
    algorithm_version: str

class ReviewListResponse(BaseModel):
    generated_at: datetime
    items: list[ReviewItem]

class ReviewActionRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    action: Literal["complete", "defer"]
    attempt_id: str | None = Field(default=None, max_length=36)
    defer_hours: int | None = Field(default=None, ge=1, le=168)

class ActivityStartRequest(BaseModel):
    client_session_id: str = Field(min_length=8, max_length=128)
    context_type: Literal["chat", "knowledge", "practice", "assessment", "exam"]
    context_id: str | None = Field(default=None, max_length=128)

class ActivityHeartbeatRequest(BaseModel):
    client_time: datetime | None = None

class ActivityItem(BaseModel):
    id: str
    client_session_id: str
    context_type: str
    context_id: str | None
    started_at: datetime
    last_heartbeat_at: datetime
    ended_at: datetime | None
    active_seconds: int
    status: str

def _user(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)

def _raise(error: LearningHubError) -> None:
    status = 404 if error.code == "REVIEW_NOT_FOUND" else 409 if error.code in {"IDEMPOTENCY_CONFLICT", "STALE_ATTEMPT"} else 422
    raise HTTPException(status, detail={"code": error.code, "message": error.message})

@router.get("/reviews/due", response_model=ReviewListResponse)
async def get_due(request: Request, limit: int = Query(20, ge=1, le=100), include_upcoming: bool = False):
    return await due_reviews(_user(request), limit=limit, include_upcoming=include_upcoming)

@router.post("/reviews/{schedule_id}/actions", response_model=ReviewItem)
async def post_action(request: Request, schedule_id: int, body: ReviewActionRequest):
    try:
        if body.action == "complete":
            if not body.attempt_id:
                raise LearningHubError("ATTEMPT_EVIDENCE_REQUIRED", "完成复习必须提供真实作答 ID")
            return await complete_review(_user(request), schedule_id, attempt_id=body.attempt_id, idempotency_key=body.idempotency_key)
        return await defer_review(_user(request), schedule_id, hours=body.defer_hours or 24, idempotency_key=body.idempotency_key)
    except LearningHubError as error:
        _raise(error)

@router.get("/today")
async def get_today(request: Request, limit: int = Query(5, ge=1, le=10)):
    return await today_hub(_user(request), limit=limit)

@router.get("/dashboard")
async def get_dashboard(request: Request, period: Literal["7d", "30d", "90d"] = "7d"):
    return await unified_dashboard(_user(request), period=period)

@router.get("/profile")
async def get_learning_profile(request: Request):
    return await unified_profile(_user(request))

@router.post("/activities", response_model=ActivityItem)
async def start_learning_activity(request: Request, body: ActivityStartRequest):
    try:
        return await start_activity(_user(request), body.client_session_id, body.context_type, body.context_id)
    except ActivityError as error:
        raise HTTPException(409 if error.code == "IDEMPOTENCY_CONFLICT" else 422, detail={"code": error.code, "message": error.message})

@router.post("/activities/{activity_id}/heartbeat", response_model=ActivityItem)
async def heartbeat_learning_activity(request: Request, activity_id: str, body: ActivityHeartbeatRequest):
    try:
        return await heartbeat_activity(_user(request), activity_id, body.client_time)
    except ActivityError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message})

@router.post("/activities/{activity_id}/end", response_model=ActivityItem)
async def end_learning_activity(request: Request, activity_id: str):
    try:
        return await end_activity(_user(request), activity_id)
    except ActivityError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message})
