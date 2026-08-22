"""学生端组卷测试 API（主系统，非 admin）。

归属：学生端学习功能，与题库导入/审核（admin 工作台）完全分离。
- POST /api/papers/generate      按参数组卷并返回试卷（剥离答案/解析，防止提前泄漏）
- GET  /api/papers/{paper_id}    试卷详情（继续作答用，同样不含答案）
- POST /api/papers/{paper_id}/submit  提交答案 → 服务端按快照 answer_spec 确定性判分

安全边界：
- 认证：任意登录用户（request.state.user_id），无需 admin
- 选题：复用 PaperGenerator 资格过滤（published + exam_eligible + auto_grading_eligible + 版本匹配）
- 判分：服务端执行（sympy 表达式等价 / 数值容差 / 布尔规范化），答案不下发客户端
- 配额：total 上限 50，防滥用
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from app.services.paper_generator import (
    PaperGenerationError,
    PaperGenerator,
    grade_paper_submission,
    normalize_config,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/papers", tags=["组卷测试-学生端（已废弃）"], deprecated=True)

_STUDENT_MAX_TOTAL = 50


def _deprecated() -> None:
    raise HTTPException(status_code=410, detail={"code": "PAPER_API_DEPRECATED", "message": "旧组卷接口已停用，请使用 /api/practice/sessions", "replacement": "/api/practice/sessions"})


def _require_user_id(request: Request) -> str:
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="未认证")
    return str(uid)


def _student_question(pq) -> Dict[str, Any]:
    """学生视角题目：剥离 answer_spec / analysis（答案与解析提交前不下发）。"""
    snap = pq.snapshot or {}
    return {
        "position": pq.position,
        "question_id": pq.question_id,
        "content": snap.get("content", ""),
        "question_type": snap.get("question_type"),
        "options": snap.get("options"),
        "difficulty": snap.get("difficulty"),
        "score": pq.score,
    }


def _student_paper(paper) -> Dict[str, Any]:
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "status": paper.status,
        "total": len(paper.questions or []),
        "created_at": paper.created_at.isoformat() if paper.created_at else None,
        "questions": [_student_question(pq) for pq in (paper.questions or [])],
    }


@router.post("/generate")
async def generate_paper(request: Request, body: Dict[str, Any]):
    """按参数组卷：config = {type_mix, total?, difficulty?, kp_codes?, random_seed?}。"""
    _require_user_id(request)
    config = body.get("config") or {}
    try:
        cfg = normalize_config(config)
    except PaperGenerationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    if cfg["total"] > _STUDENT_MAX_TOTAL:
        raise HTTPException(
            status_code=400,
            detail={"code": "TOO_LARGE", "message": f"单卷题量不能超过 {_STUDENT_MAX_TOTAL}"},
        )
    gen = PaperGenerator()
    try:
        paper = await gen.generate(config=config, title=body.get("title") or "随堂练习")
    except PaperGenerationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": _student_paper(paper)}


@router.get("/{paper_id}")
async def get_paper(request: Request, paper_id: str):
    """试卷详情（不含答案），供继续作答。"""
    _require_user_id(request)
    paper = await PaperGenerator().get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "试卷不存在"})
    return {"code": 0, "data": _student_paper(paper)}


@router.post("/{paper_id}/submit")
async def submit_paper(request: Request, paper_id: str, body: Dict[str, Any]):
    """提交答案并服务端判分：body = {answers: {question_id: answer}}。"""
    _require_user_id(request)
    paper = await PaperGenerator().get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "试卷不存在"})
    answers = body.get("answers") or {}
    if not isinstance(answers, dict):
        raise HTTPException(status_code=400, detail={"code": "BAD_ANSWERS", "message": "answers 必须是对象"})
    result = await grade_paper_submission(paper, answers)
    return {"code": 0, "data": result}
