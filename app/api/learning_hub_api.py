from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.student_contracts import STUDENT_API_RESPONSES
from app.services.learning_activity import ActivityError, end_activity, heartbeat_activity, start_activity
from app.services.learning_hub import LearningHubError, complete_review, defer_review, due_reviews, today_hub, unified_dashboard, unified_profile
from app.services.reminders import build_reminders

router = APIRouter(prefix="/api/learning", tags=["学习闭环"])

class ReviewItem(BaseModel):
    # T02：错题级排期项的 id 是 "error-{error_items.id}" 字符串，知识点级仍是整型排期 id。
    id: int | str
    knowledge_point_code: str
    knowledge_point_name: str
    due_at: datetime
    interval_days: int
    review_count: int
    stage: int
    algorithm_version: str
    # T02 错题级排期附加字段（知识点级项上为 None）
    source: Literal["knowledge_point", "error_item"] | None = None
    error_item_id: str | None = None
    question_id: str | None = None

    @field_validator("source", mode="before")
    @classmethod
    def default_source(cls, v):
        return v or "knowledge_point"

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


class TodayTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    title: str
    target_knowledge_point: dict[str, str] | None
    reason: str
    evidence: list[dict[str, Any]]
    estimated_minutes: int
    priority: int
    available_question_count: int
    start: dict[str, Any] | None
    degradation: dict[str, str] | None


class TodayHubResponse(BaseModel):
    generated_at: datetime
    algorithm_version: str
    cold_start: bool
    primary: TodayTask | None
    alternatives: list[TodayTask]


class ReminderCounts(BaseModel):
    """角标数据源：badge 用 overdue + today（需要现在处理的），upcoming 只做预览。"""

    overdue: int
    today: int
    upcoming: int
    total: int


class ReminderAction(BaseModel):
    route: str
    query: dict[str, Any] = Field(default_factory=dict)


class ReminderItem(BaseModel):
    key: str
    kind: Literal["review_schedule", "error_review"]
    bucket: Literal["overdue", "today", "upcoming"]
    source: Literal["knowledge_point", "error_item"]
    # 只有知识点级排期能被 defer；错题级排期无 deferred_until 字段（见 can_defer）。
    schedule_id: int | None = None
    error_item_id: str | None = None
    question_id: str | None = None
    knowledge_point_code: str
    knowledge_point_name: str
    due_at: datetime | None = None
    overdue_minutes: int = 0
    title: str
    hint: str
    interval_days: int | None = None
    review_count: int | None = None
    algorithm_version: str = ""
    action: ReminderAction | None = None
    can_defer: bool = False
    defer_disabled_reason: str | None = None


class RemindersResponse(BaseModel):
    generated_at: datetime
    version: str
    counts: ReminderCounts
    items: list[ReminderItem]
    primary: TodayTask | None = None


class LearningDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    generated_at: datetime
    state_version: str
    period: Literal["7d", "30d", "90d"]
    status: str
    status_message: str
    progress: dict[str, int]
    dimensions: dict[str, Any]
    weakest: list[dict[str, Any]]
    strongest: list[dict[str, Any]]
    metrics: dict[str, dict[str, Any]]
    trend: list[dict[str, Any]]
    heatmap: list[dict[str, Any]]
    chapter_mastery: list[dict[str, Any]]
    goals: dict[str, Any]
    data_quality: dict[str, Any]
    today: TodayHubResponse


class LearningProfileResponse(BaseModel):
    generated_at: datetime
    status: str
    status_message: str
    dimensions: dict[str, Any]
    review_plan: list[dict[str, Any]]
    forgetting_curve: dict[str, Any]
    insights: list[dict[str, Any]]
    data_quality: dict[str, Any]

def _user(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    return str(value)

def _raise(error: LearningHubError) -> None:
    status = 404 if error.code == "REVIEW_NOT_FOUND" else 409 if error.code in {"IDEMPOTENCY_CONFLICT", "STALE_ATTEMPT"} else 422
    raise HTTPException(status, detail={"code": error.code, "message": error.message})

@router.get("/reviews/due", response_model=ReviewListResponse, responses=STUDENT_API_RESPONSES)
async def get_due(request: Request, limit: int = Query(20, ge=1, le=100), include_upcoming: bool = False):
    return await due_reviews(_user(request), limit=limit, include_upcoming=include_upcoming)

@router.post("/reviews/{schedule_id}/actions", response_model=ReviewItem, responses=STUDENT_API_RESPONSES)
async def post_action(request: Request, schedule_id: int, body: ReviewActionRequest):
    try:
        if body.action == "complete":
            if not body.attempt_id:
                raise LearningHubError("ATTEMPT_EVIDENCE_REQUIRED", "完成复习必须提供真实作答 ID")
            return await complete_review(_user(request), schedule_id, attempt_id=body.attempt_id, idempotency_key=body.idempotency_key)
        return await defer_review(_user(request), schedule_id, hours=body.defer_hours or 24, idempotency_key=body.idempotency_key)
    except LearningHubError as error:
        _raise(error)

@router.get("/today", response_model=TodayHubResponse, responses=STUDENT_API_RESPONSES)
async def get_today(request: Request, limit: int = Query(5, ge=1, le=10)):
    return await today_hub(_user(request), limit=limit)

@router.get("/reminders", response_model=RemindersResponse, responses=STUDENT_API_RESPONSES)
async def get_reminders(request: Request, limit: int = Query(50, ge=1, le=100)):
    # 与 get_due / get_today 同口径：user_id 只能来自认证中间件写入的 request.state，
    # 提醒是派生视图，同样不得让客户端指定要看哪个用户的到期项。
    return await build_reminders(_user(request), limit=limit)

@router.get("/dashboard", response_model=LearningDashboardResponse, responses=STUDENT_API_RESPONSES)
async def get_dashboard(request: Request, period: Literal["7d", "30d", "90d"] = "7d"):
    return await unified_dashboard(_user(request), period=period)

@router.get("/profile", response_model=LearningProfileResponse, responses=STUDENT_API_RESPONSES)
async def get_learning_profile(request: Request):
    return await unified_profile(_user(request))

@router.post("/activities", response_model=ActivityItem, responses=STUDENT_API_RESPONSES)
async def start_learning_activity(request: Request, body: ActivityStartRequest):
    try:
        return await start_activity(_user(request), body.client_session_id, body.context_type, body.context_id)
    except ActivityError as error:
        raise HTTPException(409 if error.code == "IDEMPOTENCY_CONFLICT" else 422, detail={"code": error.code, "message": error.message})

@router.post("/activities/{activity_id}/heartbeat", response_model=ActivityItem, responses=STUDENT_API_RESPONSES)
async def heartbeat_learning_activity(request: Request, activity_id: str, body: ActivityHeartbeatRequest):
    try:
        return await heartbeat_activity(_user(request), activity_id, body.client_time)
    except ActivityError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message})

@router.post("/activities/{activity_id}/end", response_model=ActivityItem, responses=STUDENT_API_RESPONSES)
async def end_learning_activity(request: Request, activity_id: str):
    try:
        return await end_activity(_user(request), activity_id)
    except ActivityError as error:
        raise HTTPException(404, detail={"code": error.code, "message": error.message})
