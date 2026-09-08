"""Content Review Application Service — Step 1.1-D 人工审核闭环。

职责（仅 admin，AI_ENABLED 不影响本链路）：
- list_questions()        ：审核队列查询（review_status 过滤）
- get_question()          ：题目详情（含 candidate / source_document provenance）
- update_question()       ：编辑正式 Question（通过 domain ORM，禁止裸 SQL UPDATE）
- mark_reviewed()         ：draft → reviewed（先做服务端校验）
- publish()               ：reviewed → published（发布时再次校验）
- get_knowledge_point_catalog()：当前 24 个 KnowledgePoint（名称/code/章节）

不变量：
- 状态流严格 draft → reviewed → published；draft 不得直接 published。
- reviewed 后关键内容被编辑 → 自动回 draft，必须重新审核。
- published 题原则上不直接编辑。
- provenance（raw_parsed_content / source / parser / candidate warnings）永不被编辑覆盖；
  阻塞警告通过「依据当前内容重新校验」判定是否仍 blocking，不删除原始 warning。
"""

from __future__ import annotations

import logging
import hashlib
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.config.settings import settings
from app.data.models import (
    Chapter,
    ContentImportCandidate,
    Course,
    ImportBatch,
    KnowledgeGraphVersion,
    KnowledgePoint,
    Question,
    QuestionAuditLog,
    QuestionFeedback,
    QuestionKnowledgePoint,
    QuestionRevision,
    SourceDocument,
)
from app.services.content_ai_analysis import MOCK_AI_RESULT_NOT_PUBLISHABLE
from app.services.content_import import AUTO_GRADING_TYPES, SUPPORTED_TYPES, _strip_confirmed_answer_leak
from app.services.knowledge_seed import COURSE_CODE

logger = logging.getLogger(__name__)

# 题目可编辑字段白名单（Step 1.1-D §21；provenance 字段不在其中）
EDITABLE_QUESTION_FIELDS = {
    "content",
    "options",
    "answer",
    "analysis",
    "solution_steps",
    "difficulty",
    "estimated_time",
    "answer_spec",
    "common_mistakes",
    "variant_blueprint",
    "question_type",
    "knowledge_point_codes",
}

# 关键内容字段：修改后 reviewed → 回 draft 必须重新审核
KEY_CONTENT_FIELDS = {
    "content",
    "answer",
    "analysis",
    "options",
    "question_type",
    "answer_spec",
    "solution_steps",
    "variant_blueprint",
}

# 阻塞警告（Step 1.1-D §28；与 splitter / answer matcher 现有 code 一致）
# 注意：contains_subquestions 不作为阻塞警告 —— splitter 的启发式
# [（(]\s*\d+\s*[）)] 会把求导记号 f'(1) 误判为子题，若阻塞会导致大量
# 真实高数选择题无法审核。它保留在 candidate.warnings 中作为提示，由
# 审核员在左右对照中人工确认。
_BLOCKING_WARNING_CODES = {
    "option_parse_uncertain",
    "possible_answer_leak",
    "answer_match_missing",
    "answer_match_key_incomplete",
    "answer_roster_incomplete",
    "choice_answer_ambiguous",
    "fill_type_needs_review",
    "page_mapping_uncertain",
}


class ContentReviewError(Exception):
    """稳定 application error，携带稳定 code + 结构化校验错误。"""

    def __init__(self, code: str, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []


@dataclass
class ReviewValidation:
    ok: bool = False
    errors: List[str] = field(default_factory=list)
    blocking_warnings: List[str] = field(default_factory=list)


# ── 题型契约校验（Step 1.1-D §25-27，schema/contract 校验，不做判题引擎）──
def _choice_options_ok(options: Any) -> bool:
    if not isinstance(options, list) or len(options) < 2:
        return False
    for opt in options:
        if not isinstance(opt, dict):
            return False
        if not str(opt.get("id", "")).strip():
            return False
        if not str(opt.get("text", "")).strip():
            return False
    return True


def _choice_option_ids(options: Any) -> List[str]:
    if not isinstance(options, list):
        return []
    return [str(o.get("id", "")).strip() for o in options if isinstance(o, dict)]


def _is_valid_choice_spec(spec: Any, option_ids: List[str]) -> bool:
    if not isinstance(spec, dict):
        return False
    if spec.get("version") != 1 or spec.get("kind") != "choice":
        return False
    correct = str(spec.get("correct", "")).strip()
    return bool(correct) and correct in option_ids


def _is_valid_judge_spec(spec: Any) -> bool:
    return (
        isinstance(spec, dict)
        and spec.get("version") == 1
        and spec.get("kind") == "judge"
        and isinstance(spec.get("correct"), bool)
    )


def _is_valid_numeric_spec(spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    if spec.get("version") != 1 or spec.get("kind") != "numeric_fill":
        return False
    value = spec.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return True


def _is_valid_expression_spec(spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    if spec.get("version") != 1 or spec.get("kind") != "expression_fill":
        return False
    canonical = str(spec.get("canonical", "")).strip()
    if not canonical:
        return False
    variables = spec.get("variables") or []
    if not isinstance(variables, list):
        return False
    try:
        from app.services.safe_math import parse_safe_expression
        parse_safe_expression(canonical, variables)
    except (TypeError, ValueError):
        return False
    return True


def _choice_spec_matches_answer(spec: Any, answer: str) -> bool:
    if not isinstance(spec, dict):
        return False
    return str(spec.get("correct", "")).strip() == (answer or "").strip()


def _record_audit(
    db,
    question_id: str,
    action: str,
    from_status: Optional[str],
    to_status: Optional[str],
    operator_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """状态变化审计留痕（P0-8）。"""
    db.add(
        QuestionAuditLog(
            question_id=question_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            operator_id=operator_id,
            reason=reason,
            details=details,
        )
    )


class ContentReviewService:
    # ── 查询 ──
    async def list_questions(
        self, review_status: Optional[str] = None, limit: int = 200,
        offset: int = 0, source: Optional[str] = None,
        knowledge_point_code: Optional[str] = None,
        difficulty: Optional[int] = None, has_open_feedback: Optional[bool] = None,
    ) -> List[Question]:
        async with get_db_session() as db:
            query = select(Question).options(
                selectinload(Question.knowledge_point_links).selectinload(
                    QuestionKnowledgePoint.knowledge_point
                ),
                # provenance chain：source_candidate → import_batch → source_document
                # 序列化在 session 关闭后进行，必须在这里 eager load 否则触发 lazy load
                # 会抛 DetachedInstanceError（见 sqlalche.me/e/20/bhk3）
                selectinload(Question.source_candidate).selectinload(
                    ContentImportCandidate.import_batch
                ).selectinload(ImportBatch.source_document),
                selectinload(Question.variant_generation),
            )
            if review_status:
                query = query.where(Question.review_status == review_status)
            if source:
                query = query.where(Question.source.ilike(f"%{source}%"))
            if difficulty is not None:
                query = query.where(Question.difficulty == difficulty)
            if knowledge_point_code:
                query = query.join(QuestionKnowledgePoint).join(KnowledgePoint).where(
                    KnowledgePoint.code == knowledge_point_code
                )
            if has_open_feedback is not None:
                exists_open = select(QuestionFeedback.id).where(
                    QuestionFeedback.question_id == Question.id,
                    QuestionFeedback.status == "open",
                ).exists()
                query = query.where(exists_open if has_open_feedback else ~exists_open)
            query = query.order_by(Question.updated_at.desc()).offset(offset).limit(limit)
            rows = (await db.execute(query)).scalars().all()
            return list(rows)

    async def get_question(self, question_id: str) -> Optional[Question]:
        return await self._load_question(question_id)

    async def get_knowledge_point_catalog(self) -> List[Dict[str, Any]]:
        """当前激活课程已发布版本下的 KnowledgePoint 目录（code/name/章节）。"""
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(KnowledgePoint, Chapter.name)
                    .join(Chapter, KnowledgePoint.chapter_id == Chapter.id)
                    .join(KnowledgeGraphVersion, KnowledgePoint.version_id == KnowledgeGraphVersion.id)
                    .join(Course, KnowledgeGraphVersion.course_id == Course.id)
                    .where(
                        Course.code == COURSE_CODE,
                        Course.status == "active",
                        KnowledgeGraphVersion.status == "published",
                    )
                    .order_by(Chapter.sort_order, KnowledgePoint.sort_order, KnowledgePoint.code)
                )
            ).all()
            return [
                {"code": kp.code, "name": kp.name, "chapter": chapter_name}
                for kp, chapter_name in rows
            ]

    # ── 编辑 ──
    async def update_question(
        self, question_id: str, patch: Dict[str, Any], operator_id: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> Question:
        allowed = {k: v for k, v in (patch or {}).items() if k in EDITABLE_QUESTION_FIELDS and v is not None}
        touches_key = bool(KEY_CONTENT_FIELDS & set(allowed.keys()))

        async with get_db_session() as db:
            question = (
                await db.execute(
                    select(Question)
                    .options(selectinload(Question.knowledge_point_links))
                    .where(Question.id == question_id)
                )
            ).scalar_one_or_none()
            if question is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            before_status = question.review_status
            if before_status == "published" and touches_key and not (change_reason or "").strip():
                raise ContentReviewError("CHANGE_REASON_REQUIRED", "修改已发布题必须提供变更原因")
            if before_status == "published" and touches_key:
                db.add(QuestionRevision(
                    question_id=question.id,
                    version=question.version or 1,
                    snapshot=self._question_snapshot(question),
                    changed_by=operator_id,
                    change_reason=change_reason.strip(),
                ))
                question.version = (question.version or 1) + 1

            for k, v in allowed.items():
                if k == "knowledge_point_codes":
                    continue
                setattr(question, k, v)

            # reviewed 后关键内容修改 → 自动回 draft，必须重新审核（Step 1.1-D §33）
            if touches_key and question.review_status in {"reviewed", "published"}:
                question.review_status = "draft"
                question.practice_eligible = False
                question.exam_eligible = False
                question.auto_grading_eligible = False
                if before_status == "published":
                    from app.services.outbox import enqueue_outbox
                    await enqueue_outbox(
                        db, event_type="question.vector.delete", aggregate_type="question",
                        aggregate_id=question.id,
                        idempotency_key=f"question-vector-delete:{question.id}:v{question.version}",
                    )

            if "knowledge_point_codes" in allowed:
                codes = allowed["knowledge_point_codes"]
                if not isinstance(codes, list):
                    raise ContentReviewError("VALIDATION_FAILED", "knowledge_point_codes 必须是列表")
                known = await self._known_kp_codes(db)
                unknown = [c for c in codes if c not in known]
                if unknown:
                    raise ContentReviewError("VALIDATION_FAILED", f"未知知识点 code: {unknown}")
                await db.execute(
                    delete(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == question.id)
                )
                for i, code in enumerate(codes):
                    kp_id = (
                        await db.execute(select(KnowledgePoint.id).where(KnowledgePoint.code == code).limit(1))
                    ).scalar_one()
                    db.add(
                        QuestionKnowledgePoint(
                            question_id=question.id,
                            knowledge_point_id=kp_id,
                            is_primary=(i == 0),
                        )
                    )

            # API callers always provide an operator; keep legacy internal edits compatible.
            if allowed and operator_id:
                _record_audit(
                    db, question.id, "edited", before_status, question.review_status,
                    operator_id=operator_id, reason=change_reason,
                    details={"fields": sorted(allowed.keys()), "version": question.version},
                )
            await db.commit()

        return await self._load_question(question_id)

    # ── 状态机：draft → reviewed → published ──
    async def mark_reviewed(self, question_id: str, operator_id: Optional[str] = None) -> Question:
        async with get_db_session() as db:
            question = await self._load_in_session(db, question_id)
            if question is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            if question.review_status != "draft":
                raise ContentReviewError(
                    "STATE", f"仅 draft 可审核，当前状态 {question.review_status}"
                )
            val = await self._validate(db, question)
            if not val.ok:
                raise ContentReviewError(
                    "VALIDATION_FAILED",
                    "审核未通过: " + "; ".join(val.errors),
                    errors=val.errors,
                )
            _record_audit(db, question.id, "reviewed", "draft", "reviewed", operator_id=operator_id)
            question.review_status = "reviewed"
            if question.variant_generation is not None:
                question.variant_generation.review_status = "reviewed"
            await db.commit()
        from app.observability import CONTENT_EVENTS
        CONTENT_EVENTS.labels("review", "success").inc()
        return await self._load_question(question_id)

    async def publish(self, question_id: str, operator_id: Optional[str] = None) -> Question:
        async with get_db_session() as db:
            question = await self._load_in_session(db, question_id)
            if question is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            if question.review_status != "reviewed":
                raise ContentReviewError(
                    "STATE",
                    f"仅 reviewed 可发布，当前状态 {question.review_status}（draft 不可直接发布）",
                )
            # §18 硬性规则：AI(mock) 生成的结构化结果禁止正式发布。
            # 此校验在服务端拦截，不依赖 UI 隐藏按钮；仅真实 provider（如 qwen）
            # 生成且经人工审核的题目可被发布。
            # 开发/测试期可通过 ALLOW_MOCK_PUBLISH=true 临时旁路（仅本地/Compose，
            # 不会写死默认开启）。
            if (question.ai_provider or "") == "mock" and not getattr(settings, "ALLOW_MOCK_PUBLISH", False):
                logger.warning(
                    "拒绝发布 mock 题 %s；如需旁路请设置 ALLOW_MOCK_PUBLISH=true",
                    question_id,
                )
                raise ContentReviewError(
                    MOCK_AI_RESULT_NOT_PUBLISHABLE,
                    "AI(mock) 生成的结构化结果不可正式发布（仅可用于开发/测试）。"
                    "请接入真实 provider（如 qwen）并经人工审核后再发布；"
                    "或临时设置 ALLOW_MOCK_PUBLISH=true 旁路（仅开发环境）。",
                )
            # 发布时再次校验：不假定 reviewed 后内容未被修改
            val = await self._validate(db, question)
            if not val.ok:
                raise ContentReviewError(
                    "VALIDATION_FAILED",
                    "发布校验未通过: " + "; ".join(val.errors),
                    errors=val.errors,
                )
            question.review_status = "published"
            if question.variant_generation is not None:
                question.variant_generation.review_status = "published"
            # P0-7：发布时按题型派生判题/组卷能力（组卷只消费 exam_eligible + auto_grading_eligible 的客观题）
            objective = question.question_type in AUTO_GRADING_TYPES
            question.grading_mode = "deterministic" if objective else "manual"
            question.practice_eligible = True
            question.exam_eligible = objective
            question.auto_grading_eligible = objective
            # P0-8：发布审计（记录能力字段派生结果）
            _record_audit(
                db, question.id, "published", "reviewed", "published",
                operator_id=operator_id,
                details={
                    "grading_mode": question.grading_mode,
                    "exam_eligible": question.exam_eligible,
                    "auto_grading_eligible": question.auto_grading_eligible,
                },
            )
            from app.services.outbox import enqueue_outbox
            await enqueue_outbox(
                db, event_type="question.vector.upsert", aggregate_type="question",
                aggregate_id=question.id,
                idempotency_key=f"question-vector-upsert:{question.id}:v{question.version or 1}",
            )
            await db.commit()
        from app.observability import CONTENT_EVENTS
        CONTENT_EVENTS.labels("publish", "success").inc()
        return await self._load_question(question_id)

    async def retire(self, question_id: str, reason: str, operator_id: str) -> Question:
        if not reason.strip():
            raise ContentReviewError("REASON_REQUIRED", "退役必须提供原因")
        async with get_db_session() as db:
            question = await self._load_in_session(db, question_id)
            if question is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            if question.review_status != "published":
                raise ContentReviewError("STATE", "仅 published 题目可以退役")
            _record_audit(db, question.id, "retired", "published", "retired", operator_id, reason)
            question.review_status = "retired"
            question.practice_eligible = question.exam_eligible = question.auto_grading_eligible = False
            from app.services.outbox import enqueue_outbox
            await enqueue_outbox(
                db, event_type="question.vector.delete", aggregate_type="question",
                aggregate_id=question.id,
                idempotency_key=f"question-vector-retire:{question.id}:v{question.version or 1}",
            )
            await db.commit()
        from app.observability import CONTENT_EVENTS
        CONTENT_EVENTS.labels("retire", "success").inc()
        return await self._load_question(question_id)

    async def restore_to_draft(self, question_id: str, reason: str, operator_id: str) -> Question:
        if not reason.strip():
            raise ContentReviewError("REASON_REQUIRED", "恢复必须提供原因")
        async with get_db_session() as db:
            question = await self._load_in_session(db, question_id)
            if question is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            if question.review_status != "retired":
                raise ContentReviewError("STATE", "仅 retired 题目可以恢复")
            _record_audit(db, question.id, "restored", "retired", "draft", operator_id, reason)
            question.review_status = "draft"
            await db.commit()
        return await self._load_question(question_id)

    async def list_history(self, question_id: str) -> Dict[str, Any]:
        async with get_db_session() as db:
            revisions = (await db.execute(select(QuestionRevision).where(
                QuestionRevision.question_id == question_id).order_by(QuestionRevision.version.desc()))).scalars().all()
            audits = (await db.execute(select(QuestionAuditLog).where(
                QuestionAuditLog.question_id == question_id).order_by(QuestionAuditLog.created_at.desc()))).scalars().all()
            return {
                "revisions": [{"id": x.id, "version": x.version, "snapshot": x.snapshot,
                    "changed_by": x.changed_by, "change_reason": x.change_reason,
                    "created_at": x.created_at.isoformat() if x.created_at else None} for x in revisions],
                "audits": [{"id": x.id, "action": x.action, "from_status": x.from_status,
                    "to_status": x.to_status, "operator_id": x.operator_id, "reason": x.reason,
                    "details": x.details, "created_at": x.created_at.isoformat() if x.created_at else None} for x in audits],
            }

    async def create_feedback(self, question_id: str, issue_type: str, description: str, operator_id: str):
        if not issue_type.strip() or not description.strip():
            raise ContentReviewError("VALIDATION_FAILED", "问题类型和说明不能为空")
        async with get_db_session() as db:
            if await db.get(Question, question_id) is None:
                raise ContentReviewError("NOT_FOUND", "题目不存在")
            row = QuestionFeedback(question_id=question_id, issue_type=issue_type,
                description=description, submitted_by=operator_id)
            db.add(row); await db.commit(); await db.refresh(row)
            return self._feedback_payload(row)

    async def list_feedback(self, status: Optional[str] = None, limit: int = 100, offset: int = 0):
        async with get_db_session() as db:
            q = select(QuestionFeedback)
            if status: q = q.where(QuestionFeedback.status == status)
            rows = (await db.execute(q.order_by(QuestionFeedback.created_at.desc()).offset(offset).limit(limit))).scalars().all()
            return [self._feedback_payload(x) for x in rows]

    async def resolve_feedback(self, feedback_id: str, resolution: str, operator_id: str):
        if not resolution.strip():
            raise ContentReviewError("RESOLUTION_REQUIRED", "处置结果不能为空")
        async with get_db_session() as db:
            row = await db.get(QuestionFeedback, feedback_id)
            if row is None: raise ContentReviewError("NOT_FOUND", "反馈不存在")
            if row.status == "resolved": return self._feedback_payload(row)
            row.status, row.resolution, row.resolved_by = "resolved", resolution, operator_id
            row.resolved_at = datetime.now(timezone.utc)
            q = await db.get(Question, row.question_id)
            _record_audit(db, row.question_id, "feedback_resolved", q.review_status if q else None,
                q.review_status if q else None, operator_id, resolution, {"feedback_id": row.id})
            await db.commit(); await db.refresh(row)
            return self._feedback_payload(row)

    async def quality_audit(self, limit: int = 200) -> Dict[str, Any]:
        async with get_db_session() as db:
            questions = (await db.execute(select(Question).options(
                selectinload(Question.knowledge_point_links),
                selectinload(Question.source_candidate).selectinload(ContentImportCandidate.import_batch).selectinload(ImportBatch.source_document),
            ).limit(limit))).scalars().all()
        fingerprints: Dict[str, List[str]] = {}
        issues: List[Dict[str, Any]] = []
        kp_difficulties: Dict[str, List[int]] = {}
        question_kps: Dict[str, List[str]] = {}
        for q in questions:
            codes = [str(link.knowledge_point_id) for link in q.knowledge_point_links]
            question_kps[q.id] = codes
            for code in codes: kp_difficulties.setdefault(code, []).append(q.difficulty or 0)
            fingerprint = self._fingerprint(q.content, q.answer)
            fingerprints.setdefault(fingerprint, []).append(q.id)
            flags = []
            if not (q.answer or "").strip(): flags.append("missing_answer")
            if not (q.analysis or "").strip(): flags.append("missing_analysis")
            if not codes: flags.append("missing_knowledge_point")
            doc = q.source_candidate.import_batch.source_document if q.source_candidate and q.source_candidate.import_batch else None
            if not doc or not doc.license_type or not doc.license_confirmed_at: flags.append("missing_license")
            if (q.practice_eligible or q.exam_eligible) and not q.auto_grading_eligible: flags.append("eligibility_mismatch")
            if flags: issues.append({"question_id": q.id, "flags": flags})
        duplicates = [ids for ids in fingerprints.values() if len(ids) > 1]
        for ids in duplicates:
            for qid in ids: issues.append({"question_id": qid, "flags": ["possible_duplicate"], "duplicate_group": ids})
        for q in questions:
            for code in question_kps.get(q.id, []):
                values = kp_difficulties.get(code, [])
                if len(values) >= 5 and abs((q.difficulty or 0) - statistics.median(values)) >= 2:
                    issues.append({"question_id": q.id, "flags": ["difficulty_outlier"]})
                    break
        counts: Dict[str, int] = {}
        for issue in issues:
            for flag in issue["flags"]: counts[flag] = counts.get(flag, 0) + 1
        return {"summary": counts, "issues": issues, "duplicate_groups": duplicates}

    async def set_duplicate_disposition(self, question_id: str, duplicate_of: Optional[str],
        is_duplicate: bool, reason: str, operator_id: str) -> Dict[str, Any]:
        if not reason.strip(): raise ContentReviewError("REASON_REQUIRED", "确认原因不能为空")
        if duplicate_of == question_id: raise ContentReviewError("VALIDATION_FAILED", "题目不能与自身重复")
        async with get_db_session() as db:
            q = await db.get(Question, question_id)
            if q is None: raise ContentReviewError("NOT_FOUND", "题目不存在")
            if duplicate_of and await db.get(Question, duplicate_of) is None:
                raise ContentReviewError("NOT_FOUND", "目标重复题不存在")
            action = "duplicate_confirmed" if is_duplicate else "duplicate_dismissed"
            _record_audit(db, question_id, action, q.review_status, q.review_status,
                operator_id, reason, {"duplicate_of": duplicate_of})
            await db.commit()
        return {"question_id": question_id, "duplicate_of": duplicate_of,
            "is_duplicate": is_duplicate, "reason": reason}

    async def batch_publish(self, question_ids: List[str], operator_id: Optional[str] = None) -> Dict[str, Any]:
        """Batch publish already-reviewed questions; never bypass human review."""
        published: List[str] = []
        skipped: List[str] = []
        errors: List[Dict[str, str]] = []
        for qid in question_ids:
            try:
                q = await self._load_question(qid)
                if q is None:
                    errors.append({"question_id": qid, "error": "题目不存在"})
                    continue
                if q.review_status == "published":
                    skipped.append(qid)
                    continue
                if q.review_status != "reviewed":
                    errors.append({"question_id": qid, "error": "仅已审核题目可以批量发布"})
                    continue
                await self.publish(qid, operator_id=operator_id)
                published.append(qid)
            except ContentReviewError as e:
                errors.append({"question_id": qid, "error": f"{e.code}: {e.message}"})
            except Exception as e:  # noqa: BLE001
                errors.append({"question_id": qid, "error": str(e)[:200]})
        return {"published": published, "skipped": skipped, "errors": errors}

    # ── 校验 ──
    async def _validate(self, db, question: Question) -> ReviewValidation:
        errors: List[str] = []
        blocking: List[str] = []

        candidate = None
        if question.source_candidate_id:
            candidate = (
                await db.execute(
                    select(ContentImportCandidate).where(
                        ContentImportCandidate.id == question.source_candidate_id
                    )
                )
            ).scalar_one_or_none()
            if candidate is None:
                errors.append("来源候选缺失，provenance 不完整")
            elif candidate.import_batch and candidate.import_batch.source_document:
                doc = candidate.import_batch.source_document
                # Existing pre-4.4 sources are grandfathered and surfaced by quality audit.
                # Once license metadata is entered it must be explicitly confirmed.
                if doc.license_type and not doc.license_confirmed_at:
                    errors.append("来源许可尚未确认")

        content = (question.content or "").strip()
        if not content:
            errors.append("题干（content）不能为空")
        qtype = (question.question_type or "").strip()
        if qtype not in SUPPORTED_TYPES:
            errors.append(
                f"题型不支持：{qtype or '空'}（首版仅支持 choice / judge / numeric_fill / expression_fill）"
            )
        if not (question.answer or "").strip():
            errors.append("答案（answer）不能为空")
        if not (question.analysis or "").strip():
            errors.append("解析（analysis）不能为空")
        if not question.knowledge_point_links:
            errors.append("至少需要关联一个知识点")

        # 阻塞警告：依据当前内容重新校验（不删除 provenance 原始 warning）
        blocking = self._blocking_warnings(question, candidate)
        if blocking:
            errors.append(
                "存在未解决的阻塞警告: " + ", ".join(sorted(set(blocking)))
            )

        # 题型契约（Step 1.1-D §25-27）
        if qtype in SUPPORTED_TYPES:
            if qtype == "choice":
                option_ids = _choice_option_ids(question.options)
                if not _choice_options_ok(question.options):
                    errors.append("选择题选项无效：需要至少 2 个 {id, text} 选项")
                elif (question.answer or "").strip() not in option_ids:
                    errors.append("选择题答案必须指向真实选项")
                if not _is_valid_choice_spec(question.answer_spec, option_ids):
                    errors.append("answer_spec 无效：choice 需 {version:1, kind:'choice', correct:<选项 id>}")
                elif not _choice_spec_matches_answer(question.answer_spec, question.answer):
                    errors.append("answer_spec 与 answer 不一致")
            elif qtype == "judge":
                if not _is_valid_judge_spec(question.answer_spec):
                    errors.append("answer_spec 无效：judge 需 {version:1, kind:'judge', correct:<bool>}")
            elif qtype == "numeric_fill":
                if not _is_valid_numeric_spec(question.answer_spec):
                    errors.append("answer_spec 无效：numeric_fill 需 {version:1, kind:'numeric_fill', value:<数字>}")
            elif qtype == "expression_fill":
                if not _is_valid_expression_spec(question.answer_spec):
                    errors.append("answer_spec 无效：expression_fill 需 {version:1, kind:'expression_fill', canonical, variables}")

        return ReviewValidation(ok=not errors, errors=errors, blocking_warnings=blocking)

    @staticmethod
    def _blocking_warnings(question: Question, candidate: Optional[ContentImportCandidate]) -> List[str]:
        """依据当前内容重新判定原始 warning 是否仍阻塞（不删除 provenance）。"""
        if candidate is None:
            return []
        blocking: List[str] = []
        warnings = candidate.warnings or []
        for w in warnings:
            if w not in _BLOCKING_WARNING_CODES:
                continue
            if w == "option_parse_uncertain":
                if not _choice_options_ok(question.options):
                    blocking.append(w)
            elif w == "possible_answer_leak":
                if _stem_has_confirmed_leak(question.content, question.answer):
                    blocking.append(w)
            elif w in (
                "answer_match_missing",
                "answer_match_key_incomplete",
                "answer_roster_incomplete",
                "choice_answer_ambiguous",
            ):
                # 答案来源告警：人工补全 answer 后视为解决
                if not (question.answer or "").strip():
                    blocking.append(w)
            elif w == "fill_type_needs_review":
                # 审核员显式改为 numeric_fill/expression_fill 后视为解决
                if (question.question_type or "") == "fill":
                    blocking.append(w)
            elif w == "page_mapping_uncertain":
                # provenance 页码不可靠：审核员无法编辑 provenance，缺失即 block
                if not candidate.source_page_start or not candidate.source_page_end:
                    blocking.append(w)
        return blocking

    # ── helpers ──
    async def _load_question(self, question_id: str) -> Optional[Question]:
        async with get_db_session() as db:
            return await self._load_in_session(db, question_id)

    @staticmethod
    async def _load_in_session(db, question_id: str) -> Optional[Question]:
        return (
            await db.execute(
                select(Question)
                .options(
                    selectinload(Question.knowledge_point_links).selectinload(
                        QuestionKnowledgePoint.knowledge_point
                    ),
                    selectinload(Question.source_candidate)
                    .selectinload(ContentImportCandidate.import_batch)
                    .selectinload(ImportBatch.source_document),
                    selectinload(Question.variant_generation),
                )
                .where(Question.id == question_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _known_kp_codes(db) -> set:
        codes = (await db.execute(select(KnowledgePoint.code))).scalars().all()
        return set(codes)

    @staticmethod
    def _question_snapshot(q: Question) -> Dict[str, Any]:
        return {key: getattr(q, key) for key in (
            "content", "question_type", "options", "answer", "analysis", "solution_steps",
            "difficulty", "answer_spec", "common_mistakes", "review_status", "version",
        )}

    @staticmethod
    def _feedback_payload(row: QuestionFeedback) -> Dict[str, Any]:
        return {"id": row.id, "question_id": row.question_id, "issue_type": row.issue_type,
            "description": row.description, "status": row.status, "submitted_by": row.submitted_by,
            "resolved_by": row.resolved_by, "resolution": row.resolution,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}

    @staticmethod
    def _fingerprint(content: str, answer: str) -> str:
        normalized = "".join((content or "").lower().split()) + "|" + "".join((answer or "").lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _stem_has_confirmed_leak(stem: str, answer_letter: str) -> bool:
    _, removed = _strip_confirmed_answer_leak(stem or "", answer_letter or "")
    return removed is not None


# 轻量单例（供 API 复用）
_service: Optional[ContentReviewService] = None


def get_content_review_service() -> ContentReviewService:
    global _service
    if _service is None:
        _service = ContentReviewService()
    return _service
