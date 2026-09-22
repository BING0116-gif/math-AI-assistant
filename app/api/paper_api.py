"""Paper composition API（WS-C，仅 admin）。

能力边界（P0-7）：组卷只消费 review_status=published 且 exam_eligible +
auto_grading_eligible 的客观题（choice / judge / numeric_fill / expression_fill）；
主观题（计算/证明/简答）不入卷。生成时题目快照固化，题库后续改动不影响已生成试卷。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from app.api.content_import_api import require_admin_role
from app.data.models import PaperTemplate
from app.services.paper_generator import (
    PaperGenerationError,
    PaperGenerator,
    normalize_config,
    serialize_paper,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/papers", tags=["组卷"])


@router.post("/templates")
async def create_template(request: Request, body: Dict[str, Any]):
    """创建组卷规则模板（复用配置）。"""
    require_admin_role(request)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    try:
        cfg = normalize_config(body.get("config"))
    except PaperGenerationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    tpl = PaperTemplate(
        name=name,
        course_id=body.get("course_id") or None,
        version_id=body.get("version_id") or None,
        config=cfg,
    )
    from app.data.database import get_db_session

    async with get_db_session() as db:
        db.add(tpl)
        await db.commit()
        await db.refresh(tpl)
    return {"code": 0, "data": {"id": tpl.id, "name": tpl.name, "config": tpl.config}}


@router.get("/templates")
async def list_templates(request: Request):
    """列出组卷模板。"""
    require_admin_role(request)
    from sqlalchemy import select

    from app.data.database import get_db_session

    async with get_db_session() as db:
        rows = (await db.execute(select(PaperTemplate).order_by(PaperTemplate.created_at.desc()))).scalars().all()
    return {
        "code": 0,
        "data": [
            {
                "id": t.id,
                "name": t.name,
                "course_id": t.course_id,
                "version_id": t.version_id,
                "is_active": t.is_active,
                "config": t.config,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
    }


@router.post("/preview")
async def preview_paper(request: Request, body: Dict[str, Any]):
    """按模板/规则预览组卷结果（不落库）。"""
    require_admin_role(request)
    gen = PaperGenerator()
    try:
        result = await gen.preview(template_id=body.get("template_id"), config=body.get("config"))
    except PaperGenerationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": result}


@router.post("/generate")
async def generate_paper(request: Request, body: Dict[str, Any]):
    """按模板/规则生成试卷并落库（题目快照固化）。"""
    require_admin_role(request)
    gen = PaperGenerator()
    try:
        paper = await gen.generate(
            template_id=body.get("template_id"),
            config=body.get("config"),
            title=body.get("title"),
        )
    except PaperGenerationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": serialize_paper(paper)}


@router.get("")
@router.get("/")
async def list_papers(request: Request, limit: int = 50):
    """试卷列表（admin），含每卷题数与分值合计。"""
    require_admin_role(request)
    limit = max(1, min(int(limit), 100))
    rows = await PaperGenerator().list_papers(limit)
    return {
        "code": 0,
        "data": [
            {
                "id": paper.id,
                "template_id": paper.template_id,
                "title": paper.title,
                "course_id": paper.course_id,
                "version_id": paper.version_id,
                "status": paper.status,
                "question_total": int(total or 0),
                "total_score": round(sum(float(pq.score or 0) for pq in (paper.questions or [])), 2),
                "created_at": paper.created_at.isoformat() if paper.created_at else None,
            }
            for paper, total in rows
        ],
    }


@router.get("/{paper_id}")
async def get_paper(request: Request, paper_id: str):
    """试卷详情（含卷内题目快照）。"""
    require_admin_role(request)
    paper = await PaperGenerator().get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return {"code": 0, "data": serialize_paper(paper)}


# ──────────────────────────────────────────────────────────────────────────────
# §5.3 参数化变式题模板管理（仅 admin）：draft → 试生成抽检 → published 入池
# ──────────────────────────────────────────────────────────────────────────────
question_template_router = APIRouter(prefix="/api/admin/question-templates", tags=["题目模板"])


def _template_http_error(error) -> HTTPException:
    status_map = {
        "NOT_FOUND": 404,
        "VALIDATION_FAILED": 422,
        "ANSWER_EVALUATION_FAILED": 422,
        "SAMPLING_EXHAUSTED": 422,
        "STATE_CONFLICT": 409,
    }
    return HTTPException(status_code=status_map.get(error.code, 400), detail={"code": error.code, "message": error.message})


@question_template_router.post("")
async def create_question_template(request: Request, body: Dict[str, Any]):
    """创建参数化变式题模板（draft，需试生成抽检后发布）。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, create_template, serialize_template

    admin_user_id = getattr(request.state, "user_id", None)
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="未认证")
    try:
        template = await create_template(admin_user_id, body)
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": serialize_template(template)}


@question_template_router.get("")
async def list_question_templates(request: Request, course_id: Optional[str] = None, status: Optional[str] = None):
    """模板列表（可按课程/状态过滤）。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, list_templates, serialize_template

    try:
        rows = await list_templates(course_id=course_id, status=status)
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": [serialize_template(t) for t in rows]}


@question_template_router.get("/{template_id}")
async def get_question_template(request: Request, template_id: str):
    """模板详情。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, get_template, serialize_template

    try:
        template = await get_template(template_id)
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": serialize_template(template)}


@question_template_router.post("/{template_id}/sample")
async def sample_question_template(request: Request, template_id: str, body: Dict[str, Any] | None = None):
    """试生成样例（默认 10 个，不落库）供人工抽检；seed 可复现。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, get_template, sample_preview

    body = body or {}
    try:
        template = await get_template(template_id)
        count = int(body.get("count") or 10)
        seed = body.get("seed")
        previews = sample_preview(template, count=count, seed=int(seed) if seed is not None else None)
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": previews}


@question_template_router.post("/{template_id}/publish")
async def publish_question_template(request: Request, template_id: str):
    """发布模板：实例化题进入组卷候选池（人工抽检通过后调用）。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, serialize_template, set_template_status

    try:
        template = await set_template_status(template_id, "publish")
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": serialize_template(template)}


@question_template_router.post("/{template_id}/retire")
async def retire_question_template(request: Request, template_id: str):
    """下架模板：阻止后续实例化，已生成题与快照不受影响。"""
    require_admin_role(request)
    from app.services.question_template_service import QuestionTemplateError, serialize_template, set_template_status

    try:
        template = await set_template_status(template_id, "retire")
    except QuestionTemplateError as e:
        raise _template_http_error(e)
    return {"code": 0, "data": serialize_template(template)}
