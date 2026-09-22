"""Authenticated intelligent assessment API with explicit contracts."""
from __future__ import annotations
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.services.assessment_service import (
    create_assessment, get_assessment, preview_assessment_blueprint, readiness, save_draft,
    start_assessment, submit_assessment,
)
from app.services.practice_service import PracticeError

router = APIRouter(prefix="/api/assessments", tags=["智能检测"])


class AssessmentScope(BaseModel):
    chapter_ids: list[str] = Field(default_factory=list, max_length=30)


class CreateAssessmentRequest(BaseModel):
    goal: Literal["weakness_check", "stage_retest", "review_due", "comprehensive"]
    course_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    scope: AssessmentScope = Field(default_factory=AssessmentScope)
    current_chapter_id: str | None = Field(default=None, min_length=1, max_length=36)
    duration_minutes: Literal[15, 30, 45, 60]
    intensity: Literal["foundation", "standard", "advanced"]
    question_count: int = Field(ge=5, le=30)
    idempotency_key: str = Field(min_length=8, max_length=128)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    # §5.4 微调后创建：预览蓝图的桶经用户 ±2 调整后直接作为组卷蓝图（跳过 LLM 规划）
    blueprint_buckets: list[dict[str, Any]] | None = Field(default=None, max_length=20)


class SaveDraftRequest(BaseModel):
    answer: Any = None
    expected_version: int = Field(ge=0)


class SubmitAssessmentRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class PreviewBlueprintRequest(CreateAssessmentRequest):
    """§5.4 流式蓝图预览：与创建同构，但不落库、不消耗幂等键。"""
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


def _user(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not value: raise HTTPException(status_code=401, detail={"code":"UNAUTHENTICATED","message":"请先登录"})
    return str(value)


def _raise(error: PracticeError):
    status = 404 if error.code == "SESSION_NOT_FOUND" else 409 if error.code in {"SESSION_STATE_CONFLICT","IDEMPOTENCY_CONFLICT"} else 410 if error.code == "SESSION_EXPIRED" else 422
    raise HTTPException(status_code=status, detail={"code":error.code,"message":error.message,**error.extra})


@router.get("/readiness")
async def get_readiness(request: Request, course_id: str | None = Query(default=None, max_length=36)):
    try: return {"code":0,"data":await readiness(_user(request),course_id)}
    except PracticeError as error: _raise(error)


@router.post("/sessions")
async def post_session(request: Request, body: CreateAssessmentRequest):
    payload = body.model_dump(exclude_none=True)
    buckets = payload.pop("blueprint_buckets", None)
    planner = None
    if buckets:
        # 用户微调后的蓝图：跳过 LLM，直接按桶组卷（沿用 AssessmentPlan 校验与选题/偏差兜底）
        class _UserBucketsPlanner:
            async def plan(self, signals, inventory, question_count):
                return {"plan": {"buckets": buckets}, "source": "user_adjusted", "model": None, "latency_ms": 0, "token_usage": {}, "error_code": None}
        planner = _UserBucketsPlanner()
    try: return {"code":0,"data":await create_assessment(_user(request),payload,planner=planner)}
    except PracticeError as error: _raise(error)


@router.post("/preview-blueprint")
async def post_preview_blueprint(request: Request, body: PreviewBlueprintRequest):
    """§5.4 SSE 流式蓝图预览：meta → bucket* → done；断流/出错以 error 事件结束，前端可降级快速模式。"""
    user_id = _user(request)
    payload = {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "idempotency_key"}

    async def event_stream():
        try:
            preview = await preview_assessment_blueprint(user_id, payload)
            yield f"event: meta\ndata: {json.dumps({'planning_source': preview['planning_source'], 'model': preview['model'], 'total': preview['total'], 'quota_summary': preview['quota_summary']}, ensure_ascii=False)}\n\n"
            for bucket in (preview["plan"].get("buckets") or []):
                yield f"event: bucket\ndata: {json.dumps(bucket, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps(preview, ensure_ascii=False)}\n\n"
        except PracticeError as error:
            yield f"event: error\ndata: {json.dumps({'code': error.code, 'message': error.message, **error.extra}, ensure_ascii=False)}\n\n"
        except Exception as error:  # noqa: BLE001 — SSE 连接内异常以事件形式回传，避免悬挂
            yield f"event: error\ndata: {json.dumps({'code': 'PREVIEW_FAILED', 'message': '蓝图预览失败，请使用快速模式'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    try: return {"code":0,"data":await get_assessment(_user(request),session_id)}
    except PracticeError as error: _raise(error)


@router.post("/sessions/{session_id}/start")
async def post_start(request: Request, session_id: str):
    try: return {"code":0,"data":await start_assessment(_user(request),session_id)}
    except PracticeError as error: _raise(error)


@router.put("/sessions/{session_id}/draft-answers/{question_id}")
async def put_draft(request: Request, session_id: str, question_id: str, body: SaveDraftRequest):
    try: return {"code":0,"data":await save_draft(_user(request),session_id,question_id,body.answer,body.expected_version)}
    except PracticeError as error: _raise(error)


@router.post("/sessions/{session_id}/submit")
async def post_submit(request: Request, session_id: str, body: SubmitAssessmentRequest):
    try: return {"code":0,"data":await submit_assessment(_user(request),session_id,body.idempotency_key)}
    except PracticeError as error: _raise(error)


@router.get("/sessions/{session_id}/result")
async def get_result(request: Request, session_id: str):
    try:
        data=await get_assessment(_user(request),session_id,results=True)
        if data["status"]!="completed": raise PracticeError("SESSION_STATE_CONFLICT","请先完成检测")
        return {"code":0,"data":data}
    except PracticeError as error: _raise(error)
