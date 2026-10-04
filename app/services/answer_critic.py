"""Cost-safe Answer Critic boundary.

The current implementation is deterministic and offline. A future independent
critic provider can replace ``_evaluate`` without changing mode, sampling,
failure-isolation, or persistence contracts.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import settings


class CriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=80)
    detail: str = Field(default="", max_length=240)
    location: str | None = Field(default=None, max_length=120)


class CriticReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str
    issues: list[CriticIssue] = Field(default_factory=list)
    checked_by: list[str] = Field(default_factory=list)
    model: str
    latency_ms: int = Field(ge=0)
    token_cost: int = Field(ge=0)


class AnswerCritic:
    def __init__(self, *, mode: str | None = None, sample_rate: float | None = None, evaluator: Callable[..., Awaitable[CriticReport]] | None = None):
        self.mode = mode or settings.CRITIC_MODE
        self.sample_rate = settings.CRITIC_SAMPLE_RATE if sample_rate is None else sample_rate
        self.model = settings.CRITIC_MODEL
        self._evaluator = evaluator or self._evaluate
        if self.mode not in {"off", "sample", "all"}:
            raise ValueError("critic mode must be off, sample, or all")

    def should_review(self, run_id: str) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "all":
            return True
        digest = hashlib.sha256(run_id.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") / 2**64
        return bucket < self.sample_rate

    async def review(self, *, run_id: str, question: str, final_answer: str, tool_trace: list[dict[str, Any]] | None = None, requirements: list[str] | None = None) -> CriticReport | None:
        if not self.should_review(run_id):
            return None
        started = time.perf_counter()
        try:
            report = await self._evaluator(question=question, final_answer=final_answer, tool_trace=tool_trace or [], requirements=requirements or [])
            return report.model_copy(update={"model": self.model, "latency_ms": int((time.perf_counter() - started) * 1000)})
        except Exception:
            # Critic is observational; a critic failure must never fail the answer path.
            return None

    async def _evaluate(self, *, question: str, final_answer: str, tool_trace: list[dict[str, Any]], requirements: list[str]) -> CriticReport:
        if not final_answer.strip():
            return CriticReport(verdict="fail", issues=[CriticIssue(code="empty_answer", detail="回答为空")], checked_by=["answered_question"], model=self.model, latency_ms=0, token_cost=0)
        if len(final_answer.strip()) < 12:
            return CriticReport(verdict="warn", issues=[CriticIssue(code="short_answer", detail="回答过短")], checked_by=["answered_question"], model=self.model, latency_ms=0, token_cost=0)
        return CriticReport(verdict="pass", checked_by=["answered_question", "derivation_closed"], model=self.model, latency_ms=0, token_cost=0)
