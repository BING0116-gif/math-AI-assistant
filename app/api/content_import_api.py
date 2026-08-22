"""内容导入管理 API — 管理员专用（Step 1.1-C2 / 1.1-D）。

Step 1.1-C2 提供：
- POST  /api/admin/content/imports                                  上传 PDF（quick 同步解析；MinerU 异步任务，返回 parse_task_id）
- GET   /api/admin/content/imports                                  列出批次
- GET   /api/admin/content/imports/{id}                             批次详情
- GET   /api/admin/content/imports/{id}/candidates                  列出候选
- PATCH /api/admin/content/imports/{id}/candidates/{candidate_id}   最小编辑候选
- POST  /api/admin/content/imports/{id}/drafts                      将 supported 候选落为正式题 draft

Step 1.1-D 提供：
- POST  /api/admin/content/imports/{id}/candidates/{candidate_id}/reject   拒绝候选（保留 provenance）
- GET   /api/admin/content/source-documents/{id}                            来源文档元数据
- GET   /api/admin/content/source-documents/{id}/pages/{page}/preview       渲染来源 PDF 页为 PNG
- GET   /api/admin/content/knowledge-points                                 KnowledgePoint 目录
- GET   /api/admin/content/questions                                       审核队列（review_status 过滤）
- GET   /api/admin/content/questions/{question_id}                          题目详情（含 provenance）
- PATCH /api/admin/content/questions/{question_id}                          编辑正式 Question（reviewed 编辑回 draft）
- POST  /api/admin/content/questions/{question_id}/review                   draft → reviewed（服务端校验）
- POST  /api/admin/content/questions/{question_id}/publish                  reviewed → published（再次校验）

权限：unauthenticated → 401；student → 403；admin → allowed（复用 require_admin_role）。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from app.security.access_control import require_admin_role
from app.models.content_stats import (
    ContentCoverageData,
    ContentCoverageResponse,
    ContentStatsData,
    ContentStatsResponse,
)
from app.services.content_import import (
    ContentImportService,
    get_content_import_service,
)
from app.services.content_review import (
    ContentReviewError,
    ContentReviewService,
    get_content_review_service,
)
from app.services.content_stats import ContentStatsService, get_content_stats_service
from app.services.document_parser import (
    MODE_MINERU,
    MODE_QUICK,
    ContentParseError,
)
from app.services.content_task import (
    KIND_IMPORT_PARSE,
    enqueue_task,
    get_task,
    serialize_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/content", tags=["内容导入-管理接口"])


def _admin_user_id(request: Request) -> str:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未认证")
    return str(getattr(user, "id", ""))


def _serialize_batch(batch) -> Dict[str, Any]:
    return {
        "id": batch.id,
        "source_document_id": batch.source_document_id,
        "status": batch.status,
        "parser_name": batch.parser_name,
        "parser_version": batch.parser_version,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "error_code": batch.error_code,
        "error_message": batch.error_message,
        "stats": batch.stats or {},
    }


def _serialize_candidate(cand) -> Dict[str, Any]:
    return {
        "id": cand.id,
        "import_batch_id": cand.import_batch_id,
        "candidate_index": cand.candidate_index,
        "source_page_start": cand.source_page_start,
        "source_page_end": cand.source_page_end,
        "source_question_number": cand.source_question_number,
        "stem": cand.stem,
        "options": cand.options,
        "original_answer": cand.original_answer,
        "original_solution": cand.original_solution,
        "detected_question_type": cand.detected_question_type,
        "supported": cand.supported,
        "warnings": cand.warnings or [],
        "suggested_knowledge_point_codes": cand.suggested_knowledge_point_codes or [],
        "status": cand.status,
        "created_at": cand.created_at.isoformat() if cand.created_at else None,
        "updated_at": cand.updated_at.isoformat() if cand.updated_at else None,
    }


def _serialize_source_document(doc) -> Dict[str, Any]:
    # 只暴露显示所需 metadata；不暴露 storage_key / 绝对路径（防信息泄露）
    return {
        "id": doc.id,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _serialize_question(q) -> Dict[str, Any]:
    kp_codes = [
        link.knowledge_point.code
        for link in (q.knowledge_point_links or [])
        if link.knowledge_point is not None
    ]
    cand = q.source_candidate
    source_doc = cand.import_batch.source_document if cand and cand.import_batch else None
    candidate_payload = _serialize_candidate(cand) if cand is not None else None
    if candidate_payload is not None and cand.import_batch is not None:
        candidate_payload["parser_name"] = cand.import_batch.parser_name
        candidate_payload["parser_version"] = cand.import_batch.parser_version
    if candidate_payload is not None and source_doc is not None:
        candidate_payload["source_document"] = _serialize_source_document(source_doc)
    return {
        "id": q.id,
        "content": q.content,
        "question_type": q.question_type,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "solution_steps": q.solution_steps,
        "difficulty": q.difficulty,
        "estimated_time": q.estimated_time,
        "answer_spec": q.answer_spec,
        "common_mistakes": q.common_mistakes,
        "review_status": q.review_status,
        "is_ai_generated": q.is_ai_generated,
        "source": q.source,
        "course_id": q.course_id,
        "version_id": q.version_id,
        "source_candidate_id": q.source_candidate_id,
        "knowledge_point_codes": kp_codes,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        "candidate": candidate_payload,
    }


@router.post("/imports")
async def create_import(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form(MODE_QUICK),
    idempotency_key: Optional[str] = Form(None),
):
    """上传 PDF 并同步解析（mineru / quick）。返回批次（含解析后候选统计）。"""
    require_admin_role(request)
    admin_id = _admin_user_id(request)
    content = await file.read()
    service: ContentImportService = get_content_import_service()
    try:
        batch, created = await service.create_import(
            admin_user_id=admin_id,
            original_filename=file.filename or "untitled.pdf",
            content=content,
            mode=mode,
            idempotency_key=idempotency_key,
        )
        task_id = None
        if created:
            if mode == MODE_MINERU:
                # P0-1：MinerU 解析移出请求线程 → 投递后台任务立即返回，Worker 执行解析
                task = await enqueue_task(
                    KIND_IMPORT_PARSE,
                    batch.id,
                    payload={"mode": mode},
                    max_retries=3,
                )
                task_id = task.id
            else:
                batch = await service.parse_import(batch.id)
        data = {"batch": _serialize_batch(batch), "created": created}
        if task_id:
            data["batch"]["parse_task_id"] = task_id
        return {"code": 0, "data": data}
    except ContentParseError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    except Exception as e:  # noqa: BLE001
        logger.exception("创建导入异常")
        raise HTTPException(status_code=500, detail={"code": "INTERNAL", "message": str(e)})


@router.get("/imports")
async def list_imports(request: Request):
    """列出当前管理员的导入批次。"""
    require_admin_role(request)
    admin_id = _admin_user_id(request)
    service: ContentImportService = get_content_import_service()
    batches = await service.list_batches(admin_id)
    return {"code": 0, "data": [_serialize_batch(b) for b in batches]}


@router.get("/imports/{batch_id}")
async def get_import(request: Request, batch_id: str):
    """批次详情。"""
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    batch = await service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"code": 0, "data": _serialize_batch(batch)}


@router.get("/imports/{batch_id}/candidates")
async def list_candidates(request: Request, batch_id: str):
    """列出批次候选（重启/刷新后仍可查询，候选已持久化）。"""
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    try:
        candidates = await service.list_candidates(batch_id)
    except ContentParseError as e:
        raise HTTPException(status_code=404, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": [_serialize_candidate(c) for c in candidates]}


@router.patch("/imports/{batch_id}/candidates/{candidate_id}")
async def update_candidate(
    request: Request,
    batch_id: str,
    candidate_id: str,
    body: Dict[str, Any],
):
    """最小编辑候选（不改 provenance：raw_parsed_content / source / parser 不可改）。"""
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    try:
        cand = await service.update_candidate(batch_id, candidate_id, body or {})
    except ContentParseError as e:
        raise HTTPException(status_code=404, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": _serialize_candidate(cand)}


@router.post("/imports/{batch_id}/drafts")
async def create_drafts(
    request: Request,
    batch_id: str,
    body: Dict[str, Any],
):
    """将 supported 候选落为正式 Question draft（幂等，复用 QuestionImporter）。"""
    require_admin_role(request)
    candidate_ids: List[str] = (body or {}).get("candidate_ids", [])
    if not isinstance(candidate_ids, list) or not candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids 不能为空")
    service: ContentImportService = get_content_import_service()
    try:
        result = await service.create_drafts(batch_id, candidate_ids)
    except ContentParseError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": result}


# ════ Step 1.1-D：人工审核闭环（Minimal Content Review）════

@router.post("/imports/{batch_id}/candidates/{candidate_id}/reject")
async def reject_candidate(request: Request, batch_id: str, candidate_id: str):
    """拒绝候选（保留 provenance，仅 admin）。"""
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    try:
        cand = await service.reject_candidate(batch_id, candidate_id)
    except ContentParseError as e:
        raise HTTPException(status_code=404, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": _serialize_candidate(cand)}


@router.get("/source-documents/{id}")
async def get_source_document(request: Request, id: str):
    """来源文档元数据（仅 active；不暴露 storage_key / 绝对路径）。"""
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    doc = await service.get_source_document(id)
    if doc is None:
        raise HTTPException(status_code=404, detail="来源文档不存在")
    return {"code": 0, "data": _serialize_source_document(doc)}


@router.get("/source-documents/{id}/pages/{page}/preview")
async def preview_source_page(request: Request, id: str, page: int):
    """渲染来源 PDF 指定页为 PNG（admin-only，PyMuPDF）。

    安全：页码 bounds 校验 + storage_key 防 path traversal（service 层），
    仅返回图像字节，不暴露文件系统路径。
    """
    require_admin_role(request)
    service: ContentImportService = get_content_import_service()
    try:
        image_data = await service.render_page_preview(id, page)
    except ContentParseError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return Response(content=image_data, media_type="image/png")


@router.get("/knowledge-points")
async def list_knowledge_points(request: Request):
    """当前激活课程已发布版本的知识点目录（code/name/章节），供审核员选择。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    kps = await service.get_knowledge_point_catalog()
    return {"code": 0, "data": kps}


@router.get("/questions")
async def list_questions(request: Request, review_status: Optional[str] = None):
    """审核队列题目（按 review_status 过滤；含 provenance）。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    questions = await service.list_questions(review_status)
    return {"code": 0, "data": [_serialize_question(q) for q in questions]}


@router.get("/questions/{question_id}")
async def get_question(request: Request, question_id: str):
    """题目详情（含 candidate / source_document provenance）。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    question = await service.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return {"code": 0, "data": _serialize_question(question)}


@router.patch("/questions/{question_id}")
async def update_question(request: Request, question_id: str, body: Dict[str, Any]):
    """编辑正式 Question（白名单字段；reviewed 关键修改自动回 draft）。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    try:
        question = await service.update_question(question_id, body or {})
    except ContentReviewError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    return {"code": 0, "data": _serialize_question(question)}


@router.post("/questions/{question_id}/review")
async def mark_question_reviewed(request: Request, question_id: str):
    """标记已审核：draft → reviewed（服务端校验）。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    try:
        question = await service.mark_reviewed(question_id, operator_id=_admin_user_id(request))
    except ContentReviewError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": e.code, "message": e.message, "errors": e.errors},
        )
    return {"code": 0, "data": _serialize_question(question)}


@router.post("/questions/{question_id}/publish")
async def publish_question(request: Request, question_id: str):
    """发布：reviewed → published（发布时再次校验；draft 不可直接发布）。"""
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    try:
        question = await service.publish(question_id, operator_id=_admin_user_id(request))
    except ContentReviewError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": e.code, "message": e.message, "errors": e.errors},
        )
    return {"code": 0, "data": _serialize_question(question)}


@router.post("/questions/batch-publish")
async def batch_publish_questions(request: Request, body: Dict[str, Any]):
    """批量发布：draft/reviewed → published（一键入库）。

    仅发布真实 AI 生成且校验通过的题目；mock 结果会被跳过。
    """
    require_admin_role(request)
    service: ContentReviewService = get_content_review_service()
    question_ids = body.get("question_ids") or []
    try:
        result = await service.batch_publish(question_ids, operator_id=_admin_user_id(request))
    except ContentReviewError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": e.code, "message": e.message, "errors": e.errors},
        )
    return {"code": 0, "data": result}


@router.get("/tasks/{task_id}")
async def get_content_task(request: Request, task_id: str):
    """查询异步内容任务状态（MinerU 解析 / 其他任务，含进度与重试信息）。"""
    require_admin_role(request)
    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})
    return {"code": 0, "data": serialize_task(task)}


@router.post("/tasks/{task_id}/cancel")
async def cancel_content_task(request: Request, task_id: str):
    """取消任务：pending/retrying 立即取消；running 置取消标记由 Worker 在候选题间中断。"""
    require_admin_role(request)
    from app.services.content_task import cancel_task

    ok = await cancel_task(task_id)
    if not ok:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在或已终止"}
        )
    return {"code": 0, "data": {"cancelled": True}}


# ════ Step 1.1-E1：只读统计（Content Production Inventory）════

@router.get("/stats", response_model=ContentStatsResponse)
async def content_stats(request: Request):
    """内容生产汇总统计（只读）：Question 状态 / candidate staging / 题型 / PDF 盘点 / gap。

    admin-only。不修改任何数据。
    """
    require_admin_role(request)
    service: ContentStatsService = get_content_stats_service()
    data = await service.full_stats()
    return ContentStatsResponse(data=ContentStatsData(**data))


@router.get("/coverage", response_model=ContentCoverageResponse)
async def content_coverage(request: Request):
    """24 KP 覆盖 + 发布缺口（只读）。Coverage View 数据来源。

    admin-only。显示：Published X/100、每 KP draft/reviewed/published、分级。
    """
    require_admin_role(request)
    service: ContentStatsService = get_content_stats_service()
    items = await service.kp_coverage()
    gap = await service.gap_report()
    data = ContentCoverageData(
        target=gap["target"],
        published=gap["published"],
        remaining=gap["remaining"],
        kp_status_counts=gap["kp_status_counts"],
        kps=items,
    )
    return ContentCoverageResponse(data=data)