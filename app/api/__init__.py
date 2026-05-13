from fastapi import APIRouter

router = APIRouter(prefix="/api/memory", tags=["记忆系统"])

__all__ = ["router"]