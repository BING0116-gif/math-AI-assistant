"""Content AI Analysis service (Step 1.1-E2-A0).

职责（admin-only；AI_ENABLED / 真实 Key 缺失不影响 mock 模式）：
- analyze_candidate()    ：创建 run → provider.analyze → validate → provider.verify
                          → gate → 持久化（状态机 pending→analyzing→validating→
                          verifying→pass/doubtful/failed）
- get_latest_run() / get_history() / candidate_analysis()：查询（§36），历史全保留
- reanalyze_candidate() ：创建新 run（parent_run_id=当前 run，attempt_no+1），原结果保留
- set_human_disposition()：approve / doubtful / reject（作用于最新 run）
- create_draft_from_approved()：AI PASS + human approved → 落正式 Question(draft)，
                          标记 is_ai_generated / ai_provider
- compute_batch_stats() ：批次 AI 分析统计（§37）
- is_mock_enriched_question()：供 review service 阻止 mock 结果正式发布（§18）

不变量：
- AI 状态（run）与 Question 状态（draft→reviewed→published）严格分离（§9）。
- 第二次分析创建新 run，不直接覆盖第一次 JSON（§12）。
- 不调用任何真实 AI 网络请求（当前 provider=mock）。
- Mock 结果必须可识别且服务端禁止正式 publish（§17 / §18）。
"""

from __future__ import annotations

import asyncio
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    ContentAIAnalysisRun,
    ContentImportCandidate,
    KnowledgePoint,
    Question,
)
from app.models.content_ai import (
    ContentAIAnalysisRunOut,
    ContentAIBatchStatsData,
    ContentAIProviderStatusData,
)
from app.services.content_ai_provider import (
    DEEPSEEK_PROMPT_VERSION,
    MOCK_PROMPT_VERSION,
    QWEN_PROMPT_VERSION,
    ContentAIProvider,
    ContentAIProviderError,
    get_content_ai_provider,
    get_provider_factory,
)

logger = logging.getLogger(__name__)

# 稳定错误码（§18）
MOCK_AI_RESULT_NOT_PUBLISHABLE = "MOCK_AI_RESULT_NOT_PUBLISHABLE"

# 合法人工处置
_DISPOSITIONS = {"approved", "doubtful", "reject", "reanalyze"}


class ContentAIAnalysisError(Exception):
    """稳定 application error，携带稳定 code + message。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_run(run: ContentAIAnalysisRun) -> Dict[str, Any]:
    return ContentAIAnalysisRunOut(
        id=run.id,
        candidate_id=run.candidate_id,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        status=run.status,
        gate=run.gate,
        analysis_json=run.analysis_json,
        verifier_json=run.verifier_json,
        gate_reasons=run.gate_reasons or [],
        attempt_no=run.attempt_no,
        parent_run_id=run.parent_run_id,
        human_disposition=run.human_disposition,
        human_note=run.human_note,
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        created_at=run.created_at.isoformat() if run.created_at else None,
        updated_at=run.updated_at.isoformat() if run.updated_at else None,
    ).model_dump()


def _build_snapshot(cand: ContentImportCandidate) -> Dict[str, Any]:
    return {
        "candidate_id": cand.id,
        "detected_question_type": cand.detected_question_type,
        "options": cand.options,
        "original_answer": cand.original_answer,
        "original_solution": cand.original_solution,
        "stem": cand.stem,
        "suggested_knowledge_point_codes": cand.suggested_knowledge_point_codes or [],
    }


def _compute_gate(analysis, verifier) -> tuple[str, Optional[str], List[str]]:
    """依据 verifier.verdict + analysis 健康检查计算最终 gate（§29）。"""
    reasons: List[str] = list(verifier.issues or [])
    verdict = (verifier.verdict or "pass").lower()

    # 健康检查降级：pass 但答案自检不一致 → 至少 doubtful
    if verdict == "pass" and not getattr(analysis.answer_check, "consistent", True):
        verdict = "doubtful"
        reasons.append("answer_check inconsistent")

    if verdict == "fail":
        return "failed", "FAILED", reasons or ["[gate] verifier=fail"]
    if verdict == "doubtful":
        return "doubtful", "DOUBTFUL", reasons or ["[gate] verifier=doubtful"]
    return "pass", "PASS", reasons or ["[gate] verifier=pass"]


class ContentAIAnalysisService:
    def __init__(self, provider: Optional[ContentAIProvider] = None):
        self._provider = provider

    # ── provider 懒加载（允许测试注入）──
    def _get_provider(self) -> ContentAIProvider:
        if self._provider is not None:
            return self._provider
        return get_content_ai_provider()

    async def _load_candidate(self, candidate_id: str) -> ContentImportCandidate:
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, candidate_id)
        if cand is None:
            raise ContentAIAnalysisError("NOT_FOUND", "候选不存在")
        return cand

    async def _latest_run(self, db, candidate_id: str) -> Optional[ContentAIAnalysisRun]:
        return (
            await db.execute(
                select(ContentAIAnalysisRun)
                .where(ContentAIAnalysisRun.candidate_id == candidate_id)
                .order_by(ContentAIAnalysisRun.attempt_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _known_kp_codes(self) -> set:
        async with get_db_session() as db:
            return set((await db.execute(select(KnowledgePoint.code))).scalars().all())

    # ── 单次分析（状态机全链路）──
    async def analyze_candidate(
        self,
        candidate_id: str,
        forced_case: Optional[str] = None,
        context_extra: Optional[Dict[str, Any]] = None,
    ) -> ContentAIAnalysisRun:
        """对 candidate 走完整 AI 分析状态机并持久化（每次调用创建新 run）。

        forced_case 仅测试注入（pass/doubtful/fail）。
        """
        cand = await self._load_candidate(candidate_id)
        known_codes = await self._known_kp_codes()

        async with get_db_session() as db:
            latest = await self._latest_run(db, candidate_id)
            attempt_no = (latest.attempt_no + 1) if latest else 1
            parent_run_id = latest.id if latest else None

            # ``forced_case`` is an explicit deterministic test injection.
            # It must never leak into a configured real provider or make a
            # network request merely because a developer has credentials.
            if forced_case is not None:
                from app.services.content_ai_provider import MockContentAIProvider
                provider = MockContentAIProvider(forced_case=forced_case)
            else:
                provider = self._get_provider()
            model = getattr(provider, "model", None)
            if provider.name == "deepseek":
                prompt_version = DEEPSEEK_PROMPT_VERSION
            elif provider.name == "qwen":
                prompt_version = QWEN_PROMPT_VERSION
            else:
                prompt_version = MOCK_PROMPT_VERSION

            run = ContentAIAnalysisRun(
                candidate_id=candidate_id,
                provider=provider.name,
                model=model,
                prompt_version=prompt_version,
                status="pending",
                attempt_no=attempt_no,
                parent_run_id=parent_run_id,
                started_at=_now(),
            )
            db.add(run)
            await db.flush()
            run_id = run.id

        snapshot = _build_snapshot(cand)
        context: Dict[str, Any] = {
            "known_knowledge_point_codes": sorted(known_codes),
            "attempt_no": attempt_no,
            "previous_result": latest.analysis_json if latest else None,
            "previous_gate": latest.gate if latest else None,
        }
        if forced_case:
            context["mock_case"] = forced_case
        if context_extra:
            context.update(context_extra)

        # 阶段推进（先 pending，再 analyzing/validating/verifying，最后 terminal）
        try:
            await self._transition(run_id, "analyzing")
            # 优化：真实 provider 若支持 analyze_and_verify，则一次 LLM 调用完成分析与验证
            if hasattr(provider, "analyze_and_verify"):
                analysis, verifier = provider.analyze_and_verify(snapshot, context)
            else:
                analysis = provider.analyze(snapshot, context)
                await self._transition(run_id, "validating")
                verifier = provider.verify(analysis, snapshot, context)
            await self._transition(run_id, "verifying")

            status, gate, reasons = _compute_gate(analysis, verifier)
            await self._persist_terminal(
                run_id,
                status=status,
                gate=gate,
                analysis_json=analysis.model_dump(),
                verifier_json=verifier.model_dump(),
                gate_reasons=reasons,
            )
        except ContentAIProviderError as e:
            logger.warning("AI provider unavailable/failed for %s: %s", candidate_id, e.code)
            await self._persist_failed(run_id, e.code, e.message)
        except Exception as e:  # noqa: BLE001
            logger.exception("AI analysis failed for %s", candidate_id)
            await self._persist_failed(run_id, "ANALYSIS_FAILED", str(e)[:2000])

        async with get_db_session() as db:
            return await db.get(ContentAIAnalysisRun, run_id)

    async def _transition(self, run_id: str, status: str) -> None:
        async with get_db_session() as db:
            run = await db.get(ContentAIAnalysisRun, run_id)
            if run is not None:
                run.status = status
                await db.commit()

    async def _persist_terminal(
        self, run_id: str, status: str, gate: Optional[str],
        analysis_json: Dict[str, Any], verifier_json: Dict[str, Any],
        gate_reasons: List[str],
    ) -> None:
        async with get_db_session() as db:
            run = await db.get(ContentAIAnalysisRun, run_id)
            if run is None:
                return
            run.status = status
            run.gate = gate
            run.analysis_json = analysis_json
            run.verifier_json = verifier_json
            run.gate_reasons = gate_reasons
            run.completed_at = _now()
            await db.commit()

    async def _persist_failed(self, run_id: str, code: str, message: str) -> None:
        async with get_db_session() as db:
            run = await db.get(ContentAIAnalysisRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.gate = "FAILED"
            run.error_code = code
            run.error_message = message
            run.completed_at = _now()
            await db.commit()

    # ── 重新分析（§12 / §47）──
    async def reanalyze_candidate(
        self,
        candidate_id: str,
        reanalyze_reason: Optional[str] = None,
        forced_case: Optional[str] = None,
    ) -> ContentAIAnalysisRun:
        """创建新 run（parent=最新 run，attempt+1），原结果保留（§47）。"""
        context_extra: Dict[str, Any] = {}
        if reanalyze_reason:
            context_extra["reanalyze_reason"] = reanalyze_reason
        return await self.analyze_candidate(
            candidate_id, forced_case=forced_case, context_extra=context_extra
        )

    # ── 查询 ──
    async def get_latest_run(self, candidate_id: str) -> Optional[ContentAIAnalysisRun]:
        async with get_db_session() as db:
            return await self._latest_run(db, candidate_id)

    async def get_history(self, candidate_id: str) -> List[ContentAIAnalysisRun]:
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(ContentAIAnalysisRun)
                    .where(ContentAIAnalysisRun.candidate_id == candidate_id)
                    .order_by(ContentAIAnalysisRun.attempt_no)
                )
            ).scalars().all()
            return list(rows)

    async def candidate_analysis(self, candidate_id: str) -> Dict[str, Any]:
        """返回 latest + history（§36）。"""
        history = await self.get_history(candidate_id)
        latest = history[-1] if history else None
        return {
            "candidate_id": candidate_id,
            "latest": _serialize_run(latest) if latest else None,
            "history": [_serialize_run(r) for r in history],
        }

    # ── 批次统计（§37）──
    async def compute_batch_stats(self, batch_id: str) -> ContentAIBatchStatsData:
        async with get_db_session() as db:
            candidates = (
                await db.execute(
                    select(ContentImportCandidate)
                    .where(ContentImportCandidate.import_batch_id == batch_id)
                    .options(selectinload(ContentImportCandidate.ai_analysis_runs))
                )
            ).scalars().all()

        total = len(candidates)
        eligible = sum(1 for c in candidates if c.supported)
        unsupported = total - eligible

        # 每个 candidate 取最新 run 的状态/gate（无 run → pending/待分析）
        analyzing = validating = verifying = passed = doubtful = failed = 0
        pending = 0  # 待分析（无 run）
        for c in candidates:
            runs = sorted(c.ai_analysis_runs or [], key=lambda r: r.attempt_no)
            latest = runs[-1] if runs else None
            if latest is None:
                pending += 1
                continue
            st = latest.status
            if st == "analyzing":
                analyzing += 1
            elif st == "validating":
                validating += 1
            elif st == "verifying":
                verifying += 1
            elif st == "pass":
                passed += 1
            elif st == "doubtful":
                doubtful += 1
            elif st == "failed":
                failed += 1
            else:  # pending（已建未跑完，极少见）
                pending += 1

        analyzed = total - pending
        return ContentAIBatchStatsData(
            total=total,
            eligible=eligible,
            unsupported=unsupported,
            analyzed=analyzed,
            pending=pending,
            analyzing=analyzing,
            validating=validating,
            verifying=verifying,
            pass_=passed,
            doubtful=doubtful,
            failed=failed,
        )

    # ── 批次批量分析（§37 便捷入口）──
    async def analyze_batch(
        self,
        batch_id: str,
        *,
        concurrency: int = 5,
        analyze_unsupported: bool = True,
    ) -> Dict[str, Any]:
        """对批次内所有候选并发创建 AI 分析 run。

        - concurrency: 同时请求 DeepSeek 的最大并发数，避免触发远端限流。
        - analyze_unsupported: True 时连 calculation / proof 等 unsupported 题型也分析，
          让 AI 自主判断，不再被预设题型列表拦住。
        """
        candidates = await self._load_batch_candidates(batch_id)
        return await self._analyze_candidates(
            candidates,
            concurrency=concurrency,
            analyze_unsupported=analyze_unsupported,
        )

    async def _load_batch_candidates(self, batch_id: str) -> List[ContentImportCandidate]:
        async with get_db_session() as db:
            return list(
                (
                    await db.execute(
                        select(ContentImportCandidate).where(
                            ContentImportCandidate.import_batch_id == batch_id
                        )
                    )
                )
                .scalars()
                .all()
            )

    async def _analyze_candidates(
        self,
        candidates: List[ContentImportCandidate],
        *,
        concurrency: int = 5,
        analyze_unsupported: bool = True,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        sem = asyncio.Semaphore(max(1, concurrency))
        analyzed = 0
        skipped = 0
        errors: List[Dict[str, str]] = []
        total = len(candidates)

        async def _analyze_one(cand: ContentImportCandidate) -> None:
            nonlocal analyzed, skipped
            async with sem:
                if not analyze_unsupported and not cand.supported:
                    skipped += 1
                    if progress_callback:
                        await progress_callback(total=total, analyzed=analyzed + skipped + len(errors))
                    return
                try:
                    await self.analyze_candidate(cand.id)
                    analyzed += 1
                except ContentAIAnalysisError as e:
                    errors.append({"candidate_id": cand.id, "error": f"{e.code}: {e.message}"})
                except Exception as e:  # noqa: BLE001
                    errors.append({"candidate_id": cand.id, "error": str(e)[:200]})
                finally:
                    if progress_callback:
                        await progress_callback(total=total, analyzed=analyzed + skipped + len(errors))

        await asyncio.gather(*[_analyze_one(c) for c in candidates])
        return {
            "analyzed": analyzed,
            "skipped": skipped,
            "errors": errors,
        }

    # ── 异步批量分析任务（P0-2：持久化任务表，独立 Worker 执行）──
    async def start_analyze_batch_task(
        self,
        batch_id: str,
        *,
        concurrency: int = 5,
    ) -> str:
        """投递批量分析任务（content_tasks）并立即返回 task_id；Worker 执行，前端轮询进度。"""
        from app.services.content_task import KIND_AI_BATCH_ANALYZE, enqueue_task

        task = await enqueue_task(
            KIND_AI_BATCH_ANALYZE,
            batch_id,
            payload={"batch_id": batch_id, "concurrency": concurrency},
            max_retries=2,
        )
        return task.id

    async def get_batch_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """读取持久化任务进度（兼容旧响应结构：running/completed/failed/cancelled）。"""
        from app.services.content_task import get_task, serialize_task

        task = await get_task(task_id)
        if task is None:
            return None
        return serialize_task(task, ai_compat=True)

    # ── 人工处置（§44 / §45 / §50）──
    async def set_human_disposition(
        self,
        candidate_id: str,
        disposition: str,
        note: Optional[str] = None,
    ) -> ContentAIAnalysisRun:
        disposition = (disposition or "").strip().lower()
        if disposition not in ("approved", "doubtful", "reject"):
            raise ContentAIAnalysisError("VALIDATION_FAILED", f"非法处置: {disposition}")
        async with get_db_session() as db:
            latest = await self._latest_run(db, candidate_id)
            if latest is None:
                raise ContentAIAnalysisError("NOT_FOUND", "该候选尚无 AI 分析 run，无法处置")
            # 处置作用于最新 run；不删除 AI 历史（§44）
            latest.human_disposition = disposition
            if note is not None:
                latest.human_note = note
            await db.commit()
            await db.refresh(latest)
            return latest

    # ── AI PASS + human approved → 落正式题 draft（§19 / §52）──
    async def create_draft_from_approved(self, candidate_id: str) -> Dict[str, Any]:
        """将 human approved 的最新 AI run 的结构化字段填入正式 Question(draft)。

        不变量：
        - 不再限制 supported 题型（calculation / proof 等也可入库，由 AI 自主判断题型）；
        - 原答案（original_answer）为 ground truth，不被 AI 覆盖（§52）；
        - 标记 is_ai_generated=True 与 ai_provider=run.provider（mock 可识别）；
        - 复用 ContentImportService.create_drafts（幂等 + provenance + 校验）。
        """
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, candidate_id)
            if cand is None:
                raise ContentAIAnalysisError("NOT_FOUND", "候选不存在")
            latest = await self._latest_run(db, candidate_id)
            if latest is None:
                raise ContentAIAnalysisError("NOT_FOUND", "该候选尚无 AI 分析 run")
            if latest.human_disposition != "approved":
                raise ContentAIAnalysisError(
                    "STATE", "仅 human approved 的 AI run 可转正式题草稿"
                )
            # P0-5：必须 AI Gate=PASS 才能落草稿；存疑/失败需人工纠正后重跑 AI。
            # 专家强制覆盖属发布治理范畴（需审计记录），不在本入口提供。
            if (latest.gate or "").upper() != "PASS":
                raise ContentAIAnalysisError(
                    "STATE",
                    f"仅 AI Gate=PASS 且 human approved 的 run 可转正式题草稿（当前 gate={latest.gate or 'None'}）",
                )
            analysis = latest.analysis_json or {}

            # KP：优先 AI 结果中的合法 code；否则回退候选建议 code
            ai_kp = analysis.get("knowledge_point_codes") or []
            known = set((await db.execute(select(KnowledgePoint.code))).scalars().all())
            kp_codes = [c for c in ai_kp if c in known]
            if not kp_codes:
                kp_codes = list(cand.suggested_knowledge_point_codes or [])

            batch_id = cand.import_batch_id
            provider = latest.provider or "mock"

        # 复用 ContentImportService.create_drafts（保持幂等 / provenance / 校验一致）
        from app.services.content_import import ContentImportService

        svc = ContentImportService()
        result = await svc.create_drafts(
            batch_id,
            [candidate_id],
            ai_provider=provider,
            is_ai_generated=True,
            ai_analysis_overrides={
                "analysis": analysis.get("analysis") or cand.original_solution or "",
                "difficulty": analysis.get("difficulty", 3),
                "answer_spec": analysis.get("answer_spec"),
                "common_mistakes": analysis.get("common_mistakes") or [],
                "knowledge_point_codes": kp_codes,
            },
            skip_supported_check=True,
        )
        return result

    # ── 批量操作（简化版审核页「全部通过并入库」）──
    async def batch_set_disposition(
        self,
        candidate_ids: List[str],
        disposition: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量人工处置（仅对已有 AI run 的候选）。"""
        disposition = (disposition or "").strip().lower()
        if disposition not in ("approved", "doubtful", "reject"):
            raise ContentAIAnalysisError("VALIDATION_FAILED", f"非法处置: {disposition}")

        ok = []
        errors = []
        for cid in candidate_ids:
            try:
                await self.set_human_disposition(cid, disposition, note=note)
                ok.append(cid)
            except ContentAIAnalysisError as e:
                errors.append({"candidate_id": cid, "error": f"{e.code}: {e.message}"})
            except Exception as e:  # noqa: BLE001
                errors.append({"candidate_id": cid, "error": str(e)[:200]})
        return {"disposition": disposition, "ok": ok, "errors": errors}

    async def batch_create_drafts(self, candidate_ids: List[str]) -> Dict[str, Any]:
        """批量将 human approved 的候选落为正式 Question draft。

        幂等：已入库的 candidate 会跳过。
        """
        created: List[str] = []
        skipped: List[str] = []
        errors: List[Dict[str, str]] = []
        for cid in candidate_ids:
            try:
                res = await self.create_draft_from_approved(cid)
                created.extend(res.get("created") or [])
                skipped.extend(res.get("skipped") or [])
                errors.extend(res.get("errors") or [])
            except ContentAIAnalysisError as e:
                errors.append({"candidate_id": cid, "error": f"{e.code}: {e.message}"})
            except Exception as e:  # noqa: BLE001
                errors.append({"candidate_id": cid, "error": str(e)[:200]})
        return {"created": created, "skipped": skipped, "errors": errors}

    # ── Mock 发布保护（§18）──
    @staticmethod
    async def is_mock_enriched_question(question: Question) -> bool:
        """若 Question 的有效 enrichment 来自 mock provider，则禁止正式发布。"""
        return (question.ai_provider or "") == "mock"


# ── Provider 状态（§21 / §61）──
def get_provider_status() -> ContentAIProviderStatusData:
    return get_provider_factory().provider_status()


# 轻量单例（供 API 复用）
_service: Optional[ContentAIAnalysisService] = None


def get_content_ai_analysis_service() -> ContentAIAnalysisService:
    global _service
    if _service is None:
        _service = ContentAIAnalysisService()
    return _service
