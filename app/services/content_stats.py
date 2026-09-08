"""Content Stats Application Service — Step 1.1-E1 只读内容生产统计。

定位：唯一事实统计入口（只读）。
- 不修改 Question / ContentImportCandidate / KnowledgePoint 任何字段；
- 不触发 review / publish / reject / draft 创建；
- candidate staging 与正式 Question 严格分开统计，candidate 数不进入正式题库。

供以下调用方复用同一套统计逻辑：
- scripts/content_inventory.py     独立只读审计脚本（对接 PostgreSQL）
- GET /api/admin/content/stats      admin-only 汇总统计
- GET /api/admin/content/coverage   admin-only KP 覆盖 + 审核队列

覆盖分级（内容生产管理阈值，不是学习掌握度算法）：
    0       published -> EMPTY
    1-2     published -> CRITICAL
    3-4     published -> LOW
    5+      published -> BASELINE
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import (
    Chapter,
    ContentImportCandidate,
    Course,
    ImportBatch,
    KnowledgeGraphVersion,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    SourceDocument,
)
from app.services.content_import import SUPPORTED_TYPES
from app.services.content_review import (
    _BLOCKING_WARNING_CODES,
    _choice_option_ids,
    _is_valid_choice_spec,
    _is_valid_expression_spec,
    _is_valid_judge_spec,
    _is_valid_numeric_spec,
)
from app.services.knowledge_seed import COURSE_CODE

TARGET_PUBLISHED = 100

# candidate staging 中未支持题型（计算题/证明题/待人工判定填空题）
UNSUPPORTED_CANDIDATE_TYPES = {"calculation", "proof", "subjective", "fill", "fill_candidate", "text"}


def coverage_status(published: int) -> str:
    """Content production threshold, not a mastery algorithm."""
    if published <= 0:
        return "EMPTY"
    if published <= 2:
        return "CRITICAL"
    if published <= 4:
        return "LOW"
    return "BASELINE"


class ContentStatsService:
    # ── Question 状态 ──
    async def question_status_counts(self) -> Dict[str, int]:
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(Question.review_status, func.count(Question.id))
                    .group_by(Question.review_status)
                )
            ).all()
        counts = {status: int(n) for status, n in rows}
        return {
            "total": sum(counts.values()),
            "draft": counts.get("draft", 0),
            "reviewed": counts.get("reviewed", 0),
            "published": counts.get("published", 0),
            "retired": counts.get("retired", 0),
        }

    # ── Candidate staging（不算正式题）──
    async def candidate_staging_counts(self) -> Dict[str, Any]:
        async with get_db_session() as db:
            status_rows = (
                await db.execute(
                    select(ContentImportCandidate.status, func.count(ContentImportCandidate.id))
                    .group_by(ContentImportCandidate.status)
                )
            ).all()
            type_rows = (
                await db.execute(
                    select(ContentImportCandidate.detected_question_type, func.count(ContentImportCandidate.id))
                    .group_by(ContentImportCandidate.detected_question_type)
                )
            ).all()
            supported_total = (
                await db.execute(
                    select(func.count(ContentImportCandidate.id))
                    .where(ContentImportCandidate.supported.is_(True))
                )
            ).scalar_one()
        status_counts = {status: int(n) for status, n in status_rows}
        by_type = {t or "text": int(n) for t, n in type_rows}
        total = sum(status_counts.values())
        supported = int(supported_total)
        return {
            "total": total,
            "supported": supported,
            "unsupported": total - supported,
            "by_status": status_counts,
            "by_type": by_type,
        }

    # ── 24 KP 覆盖（仅 question_knowledge_points 规范 M:N）──
    async def kp_coverage(self) -> List[Dict[str, Any]]:
        async with get_db_session() as db:
            kp_rows = (
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
            # M:N 统计：Question.review_status per knowledge_point_id
            link_rows = (
                await db.execute(
                    select(
                        QuestionKnowledgePoint.knowledge_point_id,
                        Question.review_status,
                        func.count(func.distinct(Question.id)),
                    )
                    .join(Question, Question.id == QuestionKnowledgePoint.question_id)
                    .group_by(
                        QuestionKnowledgePoint.knowledge_point_id,
                        Question.review_status,
                    )
                )
            ).all()
        kp_id_to_code = {kp.id: kp.code for kp, _ in kp_rows}
        counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for kp_id, status, n in link_rows:
            code = kp_id_to_code.get(kp_id)
            if code is not None:  # 只统计正式 catalog 内 KP
                counts[code][status] += int(n)

        items = []
        for kp, chapter_name in kp_rows:
            per = counts.get(kp.code, {})
            published = per.get("published", 0)
            items.append({
                "code": kp.code,
                "name": kp.name,
                "chapter": chapter_name,
                "draft": per.get("draft", 0),
                "reviewed": per.get("reviewed", 0),
                "published": published,
                "status": coverage_status(published),
            })
        return items

    @staticmethod
    def kp_status_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
        out = {"EMPTY": 0, "CRITICAL": 0, "LOW": 0, "BASELINE": 0}
        for it in items:
            out[it["status"]] = out.get(it["status"], 0) + 1
        return out

    # ── 题型分布 ──
    async def type_distribution(self) -> Dict[str, Any]:
        async with get_db_session() as db:
            q_rows = (
                await db.execute(
                    select(Question.question_type, func.count(Question.id))
                    .group_by(Question.question_type)
                )
            ).all()
            c_rows = (
                await db.execute(
                    select(ContentImportCandidate.detected_question_type, func.count(ContentImportCandidate.id))
                    .group_by(ContentImportCandidate.detected_question_type)
                )
            ).all()
        formal = {t or "text": int(n) for t, n in q_rows}
        candidates = {t or "text": int(n) for t, n in c_rows}
        return {"formal": formal, "candidates": candidates}

    # ── Published Quality Audit ──
    async def published_quality_audit(self) -> Dict[str, Any]:
        async with get_db_session() as db:
            questions = (
                await db.execute(
                    select(Question)
                    .options(
                        selectinload(Question.knowledge_point_links),
                        selectinload(Question.source_candidate),
                    )
                    .where(Question.review_status == "published")
                )
            ).scalars().all()

        issues: List[Dict[str, Any]] = []
        ok_count = 0
        for q in questions:
            checks = {}
            problems: List[str] = []

            checks["supported_type"] = (q.question_type or "") in SUPPORTED_TYPES
            if not checks["supported_type"]:
                problems.append(f"题型不支持: {q.question_type or '空'}")

            content = (q.content or "").strip()
            checks["content_nonempty"] = bool(content)
            if not content:
                problems.append("题干为空")

            answer = (q.answer or "").strip()
            checks["answer_nonempty"] = bool(answer)
            if not answer:
                problems.append("答案为空")

            analysis = (q.analysis or "").strip()
            checks["analysis_nonempty"] = bool(analysis)
            if not analysis:
                problems.append("解析为空")

            checks["answer_spec_valid"] = self._answer_spec_valid(q)
            if not checks["answer_spec_valid"]:
                problems.append("answer_spec 无效或缺失")

            checks["has_kp"] = bool(q.knowledge_point_links)
            if not q.knowledge_point_links:
                problems.append("未关联知识点")

            # provenance：imported（source_candidate 链） vs legacy/manual（无 candidate 但 source 存在）
            if q.source_candidate_id is not None:
                checks["provenance"] = (
                    "imported" if q.source_candidate is not None else "broken"
                )
                if q.source_candidate is None:
                    problems.append("source_candidate 缺失（provenance 断链）")
            else:
                checks["provenance"] = "legacy/manual" if (q.source or "").strip() else "missing"
                if not (q.source or "").strip():
                    problems.append("无 source_candidate 且 source 为空（provenance 缺失）")

            checks["ok"] = not problems
            if checks["ok"]:
                ok_count += 1
            issues.append({
                "question_id": q.id,
                "question_type": q.question_type,
                "review_status": q.review_status,
                "checks": checks,
                "problems": problems,
            })

        return {
            "total": len(questions),
            "ok": ok_count,
            "has_problems": len(questions) - ok_count,
            "issues": issues,
        }

    @staticmethod
    def _answer_spec_valid(q: Question) -> bool:
        qtype = (q.question_type or "").strip()
        spec = q.answer_spec
        if qtype == "choice":
            option_ids = _choice_option_ids(q.options)
            if not _is_valid_choice_spec(spec, option_ids):
                return False
            return str(spec.get("correct", "")).strip() == (q.answer or "").strip()
        if qtype == "judge":
            return _is_valid_judge_spec(spec)
        if qtype == "numeric_fill":
            return _is_valid_numeric_spec(spec)
        if qtype == "expression_fill":
            return _is_valid_expression_spec(spec)
        return False

    # ── 学校 PDF 盘点（按 batch）──
    async def school_pdf_inventory(self) -> List[Dict[str, Any]]:
        async with get_db_session() as db:
            batches = (
                await db.execute(
                    select(ImportBatch)
                    .options(
                        selectinload(ImportBatch.source_document),
                        selectinload(ImportBatch.candidates).selectinload(
                            ContentImportCandidate.questions
                        ),
                    )
                    .order_by(ImportBatch.created_at)
                )
            ).scalars().all()

        out = []
        for b in batches:
            cands = list(b.candidates or [])
            by_type: Dict[str, int] = defaultdict(int)
            for c in cands:
                by_type[c.detected_question_type or "text"] += 1
            by_status: Dict[str, int] = defaultdict(int)
            for c in cands:
                by_status[c.status] += 1

            imported_cands = [c for c in cands if c.status == "imported" and c.questions]
            linked_questions = [q for c in imported_cands for q in (c.questions or [])]
            q_status = defaultdict(int)
            for q in linked_questions:
                q_status[q.review_status] += 1

            blocking = [
                c for c in cands
                if c.supported and c.status in ("parsed", "edited")
                and self._candidate_blocking(c)
            ]
            potential_remaining = [
                c for c in cands
                if c.supported and c.status in ("parsed", "edited")
                and not self._candidate_blocking(c)
            ]

            out.append({
                "source_document": b.source_document.original_filename if b.source_document else "",
                "batch_id": b.id,
                "status": b.status,
                "candidate_total": len(cands),
                "supported": sum(1 for c in cands if c.supported),
                "unsupported": sum(1 for c in cands if not c.supported),
                "by_type": dict(by_type),
                "by_status": dict(by_status),
                # 已落正式题的 candidate 状态（draft/reviewed/published）
                "question_draft": q_status.get("draft", 0),
                "question_reviewed": q_status.get("reviewed", 0),
                "question_published": q_status.get("published", 0),
                "blocked": len(blocking),
                "potential_remaining": len(potential_remaining),
            })
        return out

    # ── Eligible Content Queue（最值得人工审核的 candidate/draft）──
    async def eligible_queue(self, limit: int = 100) -> Dict[str, Any]:
        coverage_items = await self.kp_coverage()
        coverage_by_code = {it["code"]: it["status"] for it in coverage_items}

        async with get_db_session() as db:
            cand_rows = (
                await db.execute(
                    select(ContentImportCandidate)
                    .options(
                        selectinload(ContentImportCandidate.import_batch).selectinload(
                            ImportBatch.source_document
                        )
                    )
                    .where(
                        ContentImportCandidate.supported.is_(True),
                        ContentImportCandidate.status.in_(("parsed", "edited")),
                    )
                )
            ).scalars().all()
            draft_rows = (
                await db.execute(
                    select(Question)
                    .options(selectinload(Question.knowledge_point_links).selectinload(QuestionKnowledgePoint.knowledge_point))
                    .where(Question.review_status == "draft")
                )
            ).scalars().all()

        queue_candidates = []
        for c in cand_rows:
            kp_codes = list(c.suggested_knowledge_point_codes or [])
            levels = [coverage_by_code.get(code, "") for code in kp_codes]
            blocking = self._candidate_blocking(c)
            queue_candidates.append({
                "kind": "candidate",
                "id": c.id,
                "question_id": None,
                "type": c.detected_question_type or "text",
                "supported": True,
                "has_answer": bool((c.original_answer or "").strip()),
                "has_solution": bool((c.original_solution or "").strip()),
                "page_provenance": bool(c.source_page_start is not None and c.source_page_end is not None),
                "blocking": sorted(blocking),
                "kp_codes": kp_codes,
                "kp_status": "KP_PENDING" if not kp_codes else (min(levels) if levels else ""),
                "source_document": (
                    c.import_batch.source_document.original_filename
                    if c.import_batch and c.import_batch.source_document else ""
                ),
                "source_question_number": c.source_question_number,
            })

        queue_drafts = []
        for q in draft_rows:
            codes = [
                link.knowledge_point.code
                for link in (q.knowledge_point_links or [])
                if link.knowledge_point is not None
            ]
            levels = [coverage_by_code.get(code, "") for code in codes]
            queue_drafts.append({
                "kind": "draft",
                "id": q.id,
                "question_id": q.id,
                "type": q.question_type,
                "supported": (q.question_type or "") in SUPPORTED_TYPES,
                "has_answer": bool((q.answer or "").strip()),
                "has_solution": bool((q.analysis or "").strip()),
                "page_provenance": bool(q.source_candidate_id is not None),
                "blocking": [],
                "kp_codes": codes,
                "kp_status": "KP_PENDING" if not codes else (min(levels) if levels else ""),
                "source_document": "",
                "source_question_number": "",
            })

        # 排序优先级：
        # 1 supported 2 has_answer 3 has_solution 4 page provenance 5 无 blocking 6 KP coverage 较低
        _LEVEL_RANK = {"EMPTY": 0, "CRITICAL": 1, "LOW": 2, "BASELINE": 3, "KP_PENDING": 9, "": 9}

        def sort_key(e: Dict[str, Any]) -> Tuple[int, ...]:
            return (
                0 if e["supported"] else 1,
                0 if e["has_answer"] else 1,
                0 if e["has_solution"] else 1,
                0 if e["page_provenance"] else 1,
                len(e["blocking"]),
                _LEVEL_RANK.get(e["kp_status"], 9),
                e.get("source_question_number") or "",
                e["id"],
            )

        merged = sorted(queue_candidates + queue_drafts, key=sort_key)
        return {
            "candidate_count": len(queue_candidates),
            "draft_count": len(queue_drafts),
            "items": merged[:limit],
        }

    @staticmethod
    def _candidate_blocking(c: ContentImportCandidate) -> List[str]:
        blocking = []
        warnings = c.warnings or []
        for w in warnings:
            if w in _BLOCKING_WARNING_CODES:
                blocking.append(w)
        return blocking

    # ── Gap Report ──
    async def gap_report(self) -> Dict[str, Any]:
        status = await self.question_status_counts()
        items = await self.kp_coverage()
        return {
            "target": TARGET_PUBLISHED,
            "published": status["published"],
            "remaining": max(TARGET_PUBLISHED - status["published"], 0),
            "kp_status_counts": self.kp_status_counts(items),
            "empty_kps": [it["code"] for it in items if it["status"] == "EMPTY"],
            "critical_kps": [it["code"] for it in items if it["status"] == "CRITICAL"],
            "low_kps": [it["code"] for it in items if it["status"] == "LOW"],
            "baseline_kps": [it["code"] for it in items if it["status"] == "BASELINE"],
        }

    # ── 汇总（/stats）──
    async def full_stats(self) -> Dict[str, Any]:
        status = await self.question_status_counts()
        candidates = await self.candidate_staging_counts()
        types = await self.type_distribution()
        pdf = await self.school_pdf_inventory()
        gap = await self.gap_report()
        return {
            "question_status": status,
            "candidates": candidates,
            "type_distribution": types,
            "school_pdf_inventory": pdf,
            "gap": gap,
        }


# 轻量单例（供 API 复用）
_service: Optional[ContentStatsService] = None


def get_content_stats_service() -> ContentStatsService:
    global _service
    if _service is None:
        _service = ContentStatsService()
    return _service
