"""学习路径 API(路线图 7.1,阶段五)。

纯规则、零 LLM 的确定性路径;学生信封契约;user_id 隔离。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.student_contracts import STUDENT_API_RESPONSES, StudentEnvelope
from app.services.learning_path import build_learning_path

router = APIRouter(prefix="/api/learning/path", tags=["学习路径"])


class PathStepOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    description: str
    route: str
    status: str


class PathPointOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    mastery: float
    attempts_count: int
    mistake_count: int
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[PathStepOut] = Field(default_factory=list)


class PathWeekOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: int
    focus: str
    points: list[PathPointOut] = Field(default_factory=list)


class LearningPathData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    generator: str
    weak_threshold: float
    week_capacity: int
    weak_count: int
    user_scope: str = "owner"
    weeks: list[PathWeekOut] = Field(default_factory=list)


@router.get("", response_model=StudentEnvelope[LearningPathData], responses=STUDENT_API_RESPONSES)
async def get_my_learning_path(http_request: Request):
    """我的学习路径:薄弱知识点依赖排序 + 四步模板 + 周计划(7.1)。"""
    value = getattr(http_request.state, "user_id", None)
    if not value:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "请先登录"})
    data: dict[str, Any] = await build_learning_path(str(value))
    return {"code": 0, "data": data}
