"""Pydantic schemas for the Content AI Analysis pipeline (Step 1.1-E2-A0).

第一版冻结的结构化输出契约（§26-§29）：

- ContentAIAnalysisResult    ：单次 AI 分析的结构化结果
- ContentAIAnswerCheck       ：答案自检（official_answer / consistent / reason）
- ContentAIVerificationResult：Verifier 结果（verdict / 各维度 / issues / confidence）
- ContentAIGate              ：PASS / DOUBTFUL / FAILED（稳定英文 enum，UI 可映射中文）
- ContentAIRunStatus         ：pending / analyzing / validating / verifying / pass / doubtful / failed
- ContentAIHumanDisposition  ：approved / doubtful / reject / reanalyze

这些 schema 与具体 provider（mock / qwen）无关；mock 与未来 qwen 都输出同一种结构。

约定：所有时间字段为带时区 UTC ISO 字符串（序列化层负责本地化）。
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── 稳定枚举（数据库存稳定英文，UI 可映射中文/图标）──
class ContentAIGate(str, enum.Enum):
    PASS = "PASS"
    DOUBTFUL = "DOUBTFUL"
    FAILED = "FAILED"


class ContentAIRunStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    VALIDATING = "validating"
    VERIFYING = "verifying"
    PASS = "pass"
    DOUBTFUL = "doubtful"
    FAILED = "failed"


class ContentAIHumanDisposition(str, enum.Enum):
    APPROVED = "approved"
    DOUBTFUL = "doubtful"
    REJECT = "reject"
    REANALYZE = "reanalyze"


class ContentAIMockCase(str, enum.Enum):
    """测试注入用：强制 mock provider 输出指定 gate。生产 UI 不暴露。"""

    PASS = "pass"
    DOUBTFUL = "doubtful"
    FAIL = "fail"


# ── 结构化结果 ──
class ContentAIAnswerCheck(BaseModel):
    """答案自检（§27）。未来真实 AI 可独立求解并与原答案比对。"""

    official_answer: Optional[str] = None
    consistent: bool = True
    reason: str = ""


class ContentAIAnalysisResult(BaseModel):
    """单次 AI 分析的结构化结果（§26）。"""

    question_type: str = "choice"
    knowledge_point_codes: List[str] = Field(default_factory=list)
    difficulty: int = 2
    analysis: str = ""
    answer_spec: Optional[Dict[str, Any]] = None
    common_mistakes: List[Dict[str, Any]] = Field(default_factory=list)
    answer_check: ContentAIAnswerCheck = Field(default_factory=ContentAIAnswerCheck)
    confidence: float = 0.95
    flags: List[str] = Field(default_factory=list)


class ContentAIVerificationResult(BaseModel):
    """Verifier 结果（§28）。verdict ∈ pass / doubtful / fail。"""

    verdict: str = "pass"  # pass / doubtful / fail
    answer_consistent: bool = True
    analysis_correct: bool = True
    kp_valid: bool = True
    answer_spec_valid: bool = True
    issues: List[str] = Field(default_factory=list)
    confidence: float = 0.95


# ── 运行记录输出（§11）──
class ContentAIAnalysisRunOut(BaseModel):
    id: str
    candidate_id: str
    provider: str
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    status: str
    gate: Optional[str] = None
    analysis_json: Optional[Dict[str, Any]] = None
    verifier_json: Optional[Dict[str, Any]] = None
    gate_reasons: List[str] = Field(default_factory=list)
    attempt_no: int = 1
    parent_run_id: Optional[str] = None
    human_disposition: Optional[str] = None
    human_note: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ContentAIAnalysisResultOut(BaseModel):
    """单次 candidate 的分析结果响应：latest run + history。"""

    candidate_id: str
    latest: Optional[ContentAIAnalysisRunOut] = None
    history: List[ContentAIAnalysisRunOut] = Field(default_factory=list)


class ContentAIBatchStatsData(BaseModel):
    """批次 AI 分析统计（§37）。"""

    total: int = 0
    eligible: int = 0
    unsupported: int = 0
    analyzed: int = 0
    pending: int = 0
    analyzing: int = 0
    validating: int = 0
    verifying: int = 0
    pass_: int = Field(default=0, alias="pass")
    doubtful: int = 0
    failed: int = 0

    # 别名：pydantic 导出时把 pass_ 显示成 pass（§37 字段名）
    model_config = {"populate_by_name": True}


class ContentAIAnalysisStatsResponse(BaseModel):
    code: int = 0
    data: ContentAIBatchStatsData


class ContentAIProviderStatusData(BaseModel):
    """AI provider 能力状态（§21 / §61）。

    - mode            ：CONTENT_AI_PROVIDER 配置（mock / auto）
    - provider        ：当前实际选中的 provider（mock / qwen / none）
    - available       ：当前 provider 是否可用（mock 永远 True；qwen 需 key）
    - real_available  ：若未来配置真实 provider 且有 key，则为 True
    - reason          ：不可用原因
    """

    mode: str = "mock"
    provider: str = "mock"
    available: bool = True
    real_available: bool = False
    reason: str = "mock"


class ContentAIProviderStatusResponse(BaseModel):
    code: int = 0
    data: ContentAIProviderStatusData


# ── 请求体 ──
class ContentAIHumanDispositionRequest(BaseModel):
    disposition: str  # approved / doubtful / reject / reanalyze
    note: Optional[str] = None
    # reanalyze 专用：触发重新分析时的原因（可选）
    reanalyze_reason: Optional[str] = None
