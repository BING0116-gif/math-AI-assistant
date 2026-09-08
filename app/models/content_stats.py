"""Pydantic response models for Content Stats (Step 1.1-E1).

只读统计 API 的稳定响应契约，防止字段语义漂移。
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class KPCoverageItem(BaseModel):
    code: str
    name: str
    chapter: str
    draft: int
    reviewed: int
    published: int
    status: str  # EMPTY / CRITICAL / LOW / BASELINE


class ContentCoverageData(BaseModel):
    target: int = Field(default=100)
    published: int
    remaining: int
    kp_status_counts: Dict[str, int]
    kps: List[KPCoverageItem] = Field(default_factory=list)


class ContentCoverageResponse(BaseModel):
    code: int = 0
    data: ContentCoverageData


class ContentStatsData(BaseModel):
    question_status: Dict[str, int]
    candidates: Dict[str, Any]
    type_distribution: Dict[str, Any]
    school_pdf_inventory: List[Dict[str, Any]] = Field(default_factory=list)
    gap: Dict[str, Any]


class ContentStatsResponse(BaseModel):
    code: int = 0
    data: ContentStatsData
