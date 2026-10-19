"""Anonymous learning-effectiveness report for administrators."""
from fastapi import APIRouter, Query, Request
from app.security.access_control import require_admin_role
from app.services.learning_effectiveness import build_learning_effectiveness

router = APIRouter(prefix="/api/admin", tags=["学习效果指标"])

@router.get("/learning-effectiveness")
async def learning_effectiveness(request: Request, days: int = Query(30, ge=1, le=365)):
    require_admin_role(request)
    return {"code": 0, "data": await build_learning_effectiveness(days=days)}
