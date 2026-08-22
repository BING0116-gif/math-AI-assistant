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


@router.get("/{paper_id}")
async def get_paper(request: Request, paper_id: str):
    """试卷详情（含卷内题目快照）。"""
    require_admin_role(request)
    paper = await PaperGenerator().get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return {"code": 0, "data": serialize_paper(paper)}
