"""Capability Readiness API — 管理员专用。

提供：
- GET /api/admin/readiness/capabilities  八项教学能力的三态就绪度矩阵

设计依据：`plans/知微_能力就绪度矩阵PRD_v1.0_2026-09-07.md`。

与 `/api/health/ready` 的区别：后者回答「基础设施通不通」，
本端点回答「哪个能力用不了、为什么、怎么修」。
"""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.security.access_control import require_admin_role
from app.services.readiness_matrix import build_readiness_matrix

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/readiness", tags=["能力就绪度-管理接口"])


@router.get("/capabilities")
async def get_capabilities(request: Request):
    """返回八项能力的就绪度矩阵（ok / warning / blocker）。

    只读诊断端点：不写库、不改配置、不发起付费 LLM 调用。
    仅供管理员访问——响应含密钥尾号等运维信息。
    """
    require_admin_role(request)

    started = time.perf_counter()
    matrix = await build_readiness_matrix()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    user = getattr(request.state, "current_user", None)
    user_id = getattr(user, "id", None) or getattr(user, "username", None) or "unknown"

    logger.info(
        "readiness matrix queried by user=%s elapsed_ms=%s ok=%s warning=%s blocker=%s",
        user_id,
        elapsed_ms,
        matrix.summary.ok,
        matrix.summary.warning,
        matrix.summary.blocker,
    )

    # 存在阻断项时对每项输出 warning，便于事后排查（不记录任何密钥原文）。
    for item in matrix.capabilities:
        if item.status == "blocker":
            logger.warning("readiness blocker: %s — %s", item.id, item.reason)

    body = matrix.model_dump()
    body["elapsed_ms"] = elapsed_ms

    # 与项目其他 admin 端点保持一致的 {code, data} 包装，前端用 unwrap() 解包。
    return JSONResponse({"code": 0, "data": body, "message": "ok"})
