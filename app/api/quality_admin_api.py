"""管理员质量抽检队列（不返回原始 prompt、答案或学生标识）。"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.security.access_control import require_admin_role
from app.services.quality_review import list_review_queue, submit_review

router = APIRouter(prefix="/api/admin/quality", tags=["质量抽检-管理接口"])


class QualityReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str = Field(pattern=r"^(pass|fail)$")
    issue_codes: list[str] = Field(default_factory=list, max_length=20)


def _admin_id(request: Request) -> str:
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未认证")
    return str(getattr(user, "id", ""))


@router.get("/queue")
async def get_quality_queue(
    request: Request,
    status: str = Query("pending", pattern="^(pending|graded|all)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    require_admin_role(request)
    return {"code": 0, "data": await list_review_queue(status=status, limit=limit, offset=offset)}


@router.post("/{run_id}/verdict")
async def post_quality_verdict(run_id: str, body: QualityReviewRequest, request: Request):
    require_admin_role(request)
    try:
        result = await submit_review(run_id=run_id, reviewer_id=_admin_id(request), verdict=body.verdict, issue_codes=body.issue_codes)
    except LookupError:
        raise HTTPException(status_code=404, detail="抽检 run 不存在或未进入队列")
    return {"code": 0, "data": result}
