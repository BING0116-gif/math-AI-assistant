"""Content AI Analysis 管理 API — 管理员专用（Step 1.1-E2-A0）。

三阶段 AI Content Pipeline 的后台接口（与 content_import_api 同前缀 /api/admin/content）：

- GET   /ai-analysis/provider-status                      当前 AI provider 能力状态（§21 / §61）
- POST  /imports/{batch_id}/ai-analysis                   批次批量分析（对所有 supported 候选各建一次 run）
- GET   /imports/{batch_id}/ai-analysis/stats             批次 AI 分析统计（§37）
- POST  /candidates/{candidate_id}/ai-analysis            对单个候选启动分析（首次 / 再次均创建新 run，§12）
- POST  /candidates/{candidate_id}/ai-analysis/reanalyze  重新分析（parent=最新 run，attempt+1，§47）
- GET   /candidates/{candidate_id}/ai-analysis            单次候选分析结果：latest + history（§36）
- POST  /candidates/{candidate_id}/ai-analysis/disposition 人工处置 approve / doubtful / reject（§44 / §45）
- POST  /candidates/{candidate_id}/ai-analysis/create-draft  AI PASS + human approved → 落正式题 draft（§19 / §52）

权限：unauthenticated → 401；student → 403；admin → allowed（复用 require_admin_role）。
所有接口 admin-only；mock 模式下无需真实 Key / 网络。
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request

from app.models.content_ai import (
    ContentAIAnalysisStatsResponse,
    ContentAIProviderStatusResponse,
)
from app.security.access_control import require_admin_role
from app.services.content_ai_analysis import (
    _serialize_run,
    ContentAIAnalysisError,
    ContentAIAnalysisService,
    get_content_ai_analysis_service,
    get_provider_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/content", tags=["内容导入-AI分析"])


def _admin_user_id(request: Request) -> str:
    user = getattr(request.state, "current_user", None)
    if user is None:
        # require_admin_role 已校验，这里仅防御
        return ""
    return str(getattr(user, "id", ""))


def _map_error(e: ContentAIAnalysisError, status: int = 400):
    from fastapi import HTTPException

    return HTTPException(
        status_code=status,
        detail={"code": e.code, "message": e.message},
    )


# ════ Provider 能力状态（§21 / §61）════
@router.get("/ai-analysis/provider-status", response_model=ContentAIProviderStatusResponse)
async def provider_status(request: Request):
    """暴露当前 AI provider 能力（mock / auto / qwen），以及真实 key 是否已配置。

    admin-only。UI 据此决定是否展示「真实 AI 可用」状态，并在 provider 不可用时
    给出明确提示（mock 永远可用；qwen 当前为 stub → unavailable）。
    """
    require_admin_role(request)
    return ContentAIProviderStatusResponse(data=get_provider_status())


# ════ 批次批量分析 + 统计（§37）════
@router.post("/imports/{batch_id}/ai-analysis")
async def analyze_batch(request: Request, batch_id: str):
    """对批次内所有候选各启动一次 AI 分析（含 calculation/proof 等，不再跳过）。

    同步阻塞入口；小批量可直接用。大量题目建议用 /ai-analysis/async 异步入口 + 轮询进度。
    每次调用创建新 run（历史全保留，§12）。返回 analyzed / skipped / errors 汇总。
    """
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        result = await service.analyze_batch(batch_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("批量 AI 分析失败")
        raise _map_error(ContentAIAnalysisError("BATCH_ANALYSIS_FAILED", str(e)[:500]))
    return {"code": 0, "data": result}


@router.post("/imports/{batch_id}/ai-analysis/async")
async def analyze_batch_async(request: Request, batch_id: str):
    """启动后台批量分析任务，立即返回 task_id；前端轮询 /ai-analysis/tasks/{task_id} 看进度。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        task_id = await service.start_analyze_batch_task(batch_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("启动批量 AI 分析任务失败")
        raise _map_error(ContentAIAnalysisError("BATCH_ANALYSIS_FAILED", str(e)[:500]))
    return {"code": 0, "data": {"task_id": task_id, "batch_id": batch_id}}


@router.get("/ai-analysis/tasks/{task_id}")
async def get_analyze_batch_task(request: Request, task_id: str):
    """查询异步批量分析任务状态与进度。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    task = await service.get_batch_task(task_id)
    if task is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})
    return {"code": 0, "data": task}


@router.get("/imports/{batch_id}/ai-analysis/stats", response_model=ContentAIAnalysisStatsResponse)
async def batch_stats(request: Request, batch_id: str):
    """批次 AI 分析统计（§37）：total / eligible / analyzed / 各状态计数 / pass / doubtful / failed。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    stats = await service.compute_batch_stats(batch_id)
    return ContentAIAnalysisStatsResponse(data=stats)


# ════ 单候选 AI 分析（§36 / §12 / §47）════
@router.post("/candidates/{candidate_id}/ai-analysis")
async def analyze_candidate(
    request: Request,
    candidate_id: str,
    body: Optional[Dict[str, Any]] = None,
):
    """对单个候选启动 AI 分析（首次创建 run #1；再次调用创建 run #2 并链接 parent）。

    不接收 UI 注入的 forced_case（mock_case 仅测试 DI）；生产使用确定性哈希分布（§30）。
    """
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        run = await service.analyze_candidate(candidate_id)
    except ContentAIAnalysisError as e:
        if e.code == "NOT_FOUND":
            raise _map_error(e, status=404)
        raise _map_error(e)
    return {"code": 0, "data": _serialize_run(run)}


@router.post("/candidates/{candidate_id}/ai-analysis/reanalyze")
async def reanalyze_candidate(
    request: Request,
    candidate_id: str,
    body: Optional[Dict[str, Any]] = None,
):
    """重新分析（§47）：创建新 run（parent=最新 run，attempt+1），原结果保留。"""
    require_admin_role(request)
    reanalyze_reason = (body or {}).get("reanalyze_reason")
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        run = await service.reanalyze_candidate(
            candidate_id, reanalyze_reason=reanalyze_reason
        )
    except ContentAIAnalysisError as e:
        if e.code == "NOT_FOUND":
            raise _map_error(e, status=404)
        raise _map_error(e)
    return {"code": 0, "data": _serialize_run(run)}


@router.get("/candidates/{candidate_id}/ai-analysis")
async def candidate_analysis(request: Request, candidate_id: str):
    """单次候选 AI 分析结果：latest run + history（§36）。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    result = await service.candidate_analysis(candidate_id)
    return {"code": 0, "data": result}


# ════ 人工处置（§44 / §45）════
@router.post("/candidates/{candidate_id}/ai-analysis/disposition")
async def set_disposition(
    request: Request,
    candidate_id: str,
    body: Dict[str, Any],
):
    """人工处置：approved / doubtful / reject（作用于最新 run）。

    仅 approved 的最新 run 可被 create-draft 落正式题草稿（§52）。
    """
    require_admin_role(request)
    disposition = (body or {}).get("disposition")
    note = (body or {}).get("note")
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        run = await service.set_human_disposition(candidate_id, disposition, note=note)
    except ContentAIAnalysisError as e:
        if e.code == "NOT_FOUND":
            raise _map_error(e, status=404)
        raise _map_error(e)
    return {"code": 0, "data": _serialize_run(run)}


@router.post("/candidates/{candidate_id}/ai-analysis/create-draft")
async def create_draft_from_approved(request: Request, candidate_id: str):
    """AI PASS + human approved → 落正式 Question(draft)（§19 / §52）。

    复用 ContentImportService.create_drafts（幂等 + provenance + 校验一致）；
    标记 is_ai_generated=True 与 ai_provider=run.provider（mock 可识别，禁止正式发布，§18）。
    """
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    try:
        result = await service.create_draft_from_approved(candidate_id)
    except ContentAIAnalysisError as e:
        if e.code == "NOT_FOUND":
            raise _map_error(e, status=404)
        raise _map_error(e)
    return {"code": 0, "data": result}


# ════ 批量操作（简化审核页「全部通过并入库」）════
@router.post("/candidates/ai-analysis/batch-disposition")
async def batch_set_disposition(request: Request, body: Dict[str, Any]):
    """批量人工处置：对多个 candidate 的最新 run 设置 approved / doubtful / reject。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    candidate_ids = body.get("candidate_ids") or []
    disposition = body.get("disposition")
    note = body.get("note")
    try:
        result = await service.batch_set_disposition(candidate_ids, disposition, note=note)
    except ContentAIAnalysisError as e:
        raise _map_error(e)
    return {"code": 0, "data": result}


@router.post("/candidates/ai-analysis/batch-create-drafts")
async def batch_create_drafts(request: Request, body: Dict[str, Any]):
    """批量将 human approved 的候选落为正式 Question draft。"""
    require_admin_role(request)
    service: ContentAIAnalysisService = get_content_ai_analysis_service()
    candidate_ids = body.get("candidate_ids") or []
    try:
        result = await service.batch_create_drafts(candidate_ids)
    except ContentAIAnalysisError as e:
        raise _map_error(e)
    return {"code": 0, "data": result}
