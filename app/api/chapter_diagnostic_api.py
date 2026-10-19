"""Chapter diagnostic and retest loop built on immutable assessment sessions."""
from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.student_contracts import STUDENT_API_RESPONSES, StudentOperationEnvelope
from app.data.database import get_db_session
from app.data.models import PracticeSession, KnowledgePoint, KnowledgePointResource, UserKnowledgeState, Chapter
from app.services.assessment_service import create_assessment, get_assessment, start_assessment, save_draft, submit_assessment
from app.services.practice_service import PracticeError
from app.services.chapter_scope import expand_chapter_scope

router = APIRouter(prefix="/api/chapter-diagnostics", tags=["章节诊断"])

class CreateDiagnosticRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    chapter_id: str = Field(min_length=1, max_length=36)
    duration_minutes: Literal[15, 30, 45, 60] = 30
    question_count: int = Field(default=10, ge=5, le=30)
    idempotency_key: str = Field(min_length=8, max_length=128)

class AnswerRequest(BaseModel):
    answer: Any = None
    expected_version: int = Field(ge=0)

class SubmitRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)

def _user(request: Request) -> str:
    uid = getattr(request.state, "user_id", None)
    if not uid: raise HTTPException(401, detail={"code":"UNAUTHENTICATED", "message":"请先登录"})
    return str(uid)

def _raise(error: PracticeError):
    status = 404 if error.code == "SESSION_NOT_FOUND" else 409 if error.code in {"SESSION_STATE_CONFLICT", "IDEMPOTENCY_CONFLICT"} else 422
    raise HTTPException(status, detail={"code": error.code, "message": error.message, **error.extra})

async def _enrich(user_id: str, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    async with get_db_session() as db:
        session = (await db.execute(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user_id))).scalar_one_or_none()
        if not session: raise PracticeError("SESSION_NOT_FOUND", "检测会话不存在")
        cfg = session.config_snapshot or {}
        chapter_id = cfg.get("chapter_id")
        chapter_ids = await expand_chapter_scope(db, {chapter_id}, session.course_id, session.version_id)
        points = list((await db.execute(select(KnowledgePoint).where(KnowledgePoint.course_id == session.course_id, KnowledgePoint.version_id == session.version_id, KnowledgePoint.chapter_id.in_(chapter_ids), KnowledgePoint.status == "active").order_by(KnowledgePoint.sort_order))).scalars())
        codes = {p.code for p in points}
        breakdown = {r["knowledge_point_code"]: r for r in (data.get("knowledge_breakdown") or []) if r.get("knowledge_point_code") in codes}
        weak = [{"knowledge_point_code": p.code, "name": p.name, "accuracy": round(float(breakdown[p.code].get("accuracy", 0)), 3), "reason": "章节诊断正确率低于 60%"} for p in points if p.code in breakdown and float(breakdown[p.code].get("accuracy", 0)) < 0.6]
        weak_codes = {item["knowledge_point_code"] for item in weak}
        weak_ids = [p.id for p in points if p.code in weak_codes]
        resources = list((await db.execute(select(KnowledgePointResource).where(KnowledgePointResource.knowledge_point_id.in_(weak_ids), KnowledgePointResource.status == "published").order_by(KnowledgePointResource.sort_order))).scalars()) if weak_ids else []
        data["diagnostic_kind"] = cfg.get("diagnostic_kind", "diagnostic")
        data["chapter_id"] = chapter_id
        data["weak_points"] = weak
        data["untested_points"] = [{"knowledge_point_code": p.code, "name": p.name} for p in points if p.code not in breakdown]
        data["recommended_resources"] = [{"id": r.id, "knowledge_point_id": r.knowledge_point_id, "type": r.resource_type, "title": r.title, "body": r.body} for r in resources[:20]]
        data["mastery_comparison"] = {"before": cfg.get("mastery_before", {}), "after": {code: round(float(row.get("accuracy", 0)), 3) for code, row in breakdown.items()} if data.get("status") == "completed" else {}}
        return data

@router.post("", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def create(request: Request, body: CreateDiagnosticRequest):
    uid = _user(request)
    async with get_db_session() as db:
        chapter = (await db.execute(select(Chapter).where(Chapter.id == body.chapter_id, Chapter.course_id == body.course_id, Chapter.version_id == body.version_id, Chapter.status == "published"))).scalar_one_or_none()
        if not chapter: raise HTTPException(404, detail={"code":"CHAPTER_NOT_FOUND", "message":"章节不存在或未发布"})
        states = list((await db.execute(select(UserKnowledgeState).where(UserKnowledgeState.user_id == uid))).scalars())
    cfg = body.model_dump() | {"goal":"weakness_check", "intensity":"standard", "current_chapter_id":body.chapter_id, "scope":{"chapter_ids":[body.chapter_id]}, "diagnostic_kind":"diagnostic", "mastery_before":{s.knowledge_point_code: round(float(s.mastery or 0), 3) for s in states}}
    try:
        result = await create_assessment(uid, cfg)
        return {"code":0, "data": await _enrich(uid, result["session_id"], result)}
    except PracticeError as e: _raise(e)

@router.post("/{session_id}/retest", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def retest(request: Request, session_id: str, body: CreateDiagnosticRequest):
    uid = _user(request)
    async with get_db_session() as db:
        baseline = (await db.execute(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == uid))).scalar_one_or_none()
        if not baseline: raise HTTPException(404, detail={"code":"SESSION_NOT_FOUND", "message":"诊断会话不存在"})
        baseline_cfg = baseline.config_snapshot or {}
        if baseline.status != "completed": raise HTTPException(409, detail={"code":"DIAGNOSTIC_NOT_COMPLETED", "message":"请先完成诊断后再复测"})
        if baseline_cfg.get("chapter_id") != body.chapter_id: raise HTTPException(409, detail={"code":"CHAPTER_MISMATCH", "message":"复测必须使用原诊断章节"})
        baseline_result = await get_assessment(uid, session_id, results=True)
        mastery_before = {row.get("knowledge_point_code"): round(float(row.get("accuracy", 0)), 3) for row in (baseline_result.get("knowledge_breakdown") or [])}
    cfg = body.model_dump() | {"goal":"stage_retest", "intensity":"standard", "current_chapter_id":body.chapter_id, "scope":{"chapter_ids":[body.chapter_id]}, "diagnostic_kind":"retest", "baseline_session_id":session_id, "mastery_before": mastery_before}
    try:
        result = await create_assessment(uid, cfg)
        return {"code":0, "data": await _enrich(uid, result["session_id"], result)}
    except PracticeError as e: _raise(e)

@router.get("/{session_id}", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def get(request: Request, session_id: str):
    try:
        uid = _user(request); data = await get_assessment(uid, session_id, results=True)
        return {"code":0, "data": await _enrich(uid, session_id, data)}
    except PracticeError as e: _raise(e)

@router.post("/{session_id}/start", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def start(request: Request, session_id: str):
    try: return {"code":0, "data": await start_assessment(_user(request), session_id)}
    except PracticeError as e: _raise(e)

@router.put("/{session_id}/answers/{question_id}", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def answer(request: Request, session_id: str, question_id: str, body: AnswerRequest):
    try: return {"code":0, "data": await save_draft(_user(request), session_id, question_id, body.answer, body.expected_version)}
    except PracticeError as e: _raise(e)

@router.post("/{session_id}/submit", response_model=StudentOperationEnvelope, responses=STUDENT_API_RESPONSES)
async def submit(request: Request, session_id: str, body: SubmitRequest):
    try:
        uid = _user(request); data = await submit_assessment(uid, session_id, body.idempotency_key)
        return {"code":0, "data": await _enrich(uid, session_id, data)}
    except PracticeError as e: _raise(e)
