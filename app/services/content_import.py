"""Content Import Application Service — 内容导入唯一应用服务。

职责（Step 1.1-C2）：
- create_import()   ：上传校验 + 建 SourceDocument + ImportBatch（幂等）
- parse_import()    ：DocumentParser + QuestionSplitter → 持久化 ContentImportCandidate
- list_candidates() ：按批次列出候选
- update_candidate(): 最小编辑（不改 provenance 字段）
- create_drafts()   ：将 supported candidate 落为正式 Question draft（复用 QuestionImporter）

约定：
- 最终落正式题必须调用 QuestionImporter，禁止本服务直接 session.add(Question(...))。
- AI 不参与本 C2 链路（AI_ENABLED 不影响导入）。
- candidate.supported=False（calculation/proof/subjective/unknown）不转正式 Question。
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import (
    ContentImportCandidate,
    ImportBatch,
    Question,
    SourceDocument,
)
from app.services.document_parser import (
    MODE_MINERU,
    MODE_QUICK,
    ContentParseError,
    DocumentParser,
    validate_pdf_page_count,
    validate_pdf_upload,
)
from app.services.content_answer_matcher import (
    MATCHED,
    ContentAnswerMatcher,
    classify_fill_subtype,
)
from app.services.knowledge_seed import COURSE_CODE
from app.services.question_importer import QuestionImporter
from app.services.question_splitter import (
    guess_option_letters,
    split_document,
)

logger = logging.getLogger(__name__)

# 首版正式自动判题支持题型
# 为简化用户流程，扩展可入库题型。新题型（calculation / proof / short_answer）
# answer_spec 使用通用 text 格式，后续判题引擎可逐步支持。
SUPPORTED_TYPES = {"choice", "judge", "numeric_fill", "expression_fill", "calculation", "proof", "short_answer"}

# 可自动判题（确定性）题型：首版组卷只从这些题型出题（用户决策：暂不含计算/证明/简答等主观题）。
AUTO_GRADING_TYPES = {"choice", "judge", "numeric_fill", "expression_fill"}


def auto_grading_eligible_for(qtype: Optional[str]) -> bool:
    return (qtype or "") in AUTO_GRADING_TYPES


def grading_mode_for(qtype: Optional[str]) -> str:
    """确定性题型 → deterministic；其余 → manual（llm_assisted 留给后续）。"""
    return "deterministic" if auto_grading_eligible_for(qtype) else "manual"

# 批次状态
BATCH_PENDING = "pending"
BATCH_PARSING = "parsing"
BATCH_PARSED = "parsed"
BATCH_FAILED = "failed"
BATCH_COMPLETED = "completed"

# candidate 状态
CAND_PARSED = "parsed"
CAND_EDITED = "edited"
CAND_IMPORTED = "imported"
CAND_REJECTED = "rejected"

# candidate 可编辑字段（更新白名单）
EDITABLE_CANDIDATE_FIELDS = {
    "stem",
    "options",
    "original_answer",
    "original_solution",
    "detected_question_type",
    "suggested_knowledge_point_codes",
}

_ANSWER_LEAK_RE = re.compile(r"([）)])([A-Da-d])(?=\s*[A-Da-d]\b)")


def _strip_confirmed_answer_leak(stem: str, answer_letter: str):
    """题干尾部 '（ ）B' 泄漏：仅当泄漏字母与官方答案一致才剥离。

    返回 (new_stem, removed_letter)。无法确认时不剥离（返回原题、None），
    由调用方保持 warning 且不支持发布 —— 不自动修得'看起来对'。
    """
    if not answer_letter or answer_letter.upper() not in ("A", "B", "C", "D"):
        return stem, None
    m = _ANSWER_LEAK_RE.search(stem or "")
    if not m or m.group(2).upper() != answer_letter.upper():
        return stem, None
    return stem[:m.start()] + m.group(1) + stem[m.end():], m.group(2).upper()


class ContentImportService:
    def __init__(self, parser: Optional[DocumentParser] = None, importer: Optional[QuestionImporter] = None):
        self._parser = parser or DocumentParser()
        self._importer = importer or QuestionImporter()

    # ── 存储路径 helpers ──
    def _storage_root(self) -> Path:
        root = Path(settings.CONTENT_STORAGE_ROOT)
        if not root.is_absolute():
            root = Path.cwd() / root
        return root

    # ── create_import ──
    async def create_import(
        self,
        admin_user_id: str,
        original_filename: str,
        content: bytes,
        mode: str = MODE_QUICK,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[ImportBatch, bool]:
        """创建来源文档与 pending 批次。返回 (batch, created)。

        幂等：同一 admin + idempotency_key 已存在时返回既有批次（created=False），不重复创建。
        """
        validate_pdf_upload(content, original_filename)
        if mode not in (MODE_QUICK, MODE_MINERU):
            raise ContentParseError("PARSE_FAILED", f"未知解析模式: {mode}")

        if idempotency_key:
            async with get_db_session() as db:
                existing = (
                    await db.execute(
                        select(ImportBatch)
                        .where(
                            ImportBatch.created_by == admin_user_id,
                            ImportBatch.idempotency_key == idempotency_key,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return existing, False

        sha256 = hashlib.sha256(content).hexdigest()
        storage_key = self._store_original(content, original_filename)

        async with get_db_session() as db:
            source_doc = SourceDocument(
                original_filename=original_filename,
                storage_key=storage_key,
                sha256=sha256,
                mime_type="application/pdf",
                size_bytes=len(content),
                created_by=admin_user_id,
                status="active",
            )
            db.add(source_doc)
            await db.flush()
            batch = ImportBatch(
                source_document_id=source_doc.id,
                status=BATCH_PENDING,
                parser_name=mode,
                parser_version="",
                created_by=admin_user_id,
                idempotency_key=idempotency_key,
                stats={},
            )
            db.add(batch)
            await db.commit()
            await db.refresh(batch)
            return batch, True

    def _store_original(self, content: bytes, original_filename: str) -> str:
        """写入 CONTENT_STORAGE_ROOT/originals/{uuid}.pdf，返回相对 storage_key。"""
        root = self._storage_root()
        originals_dir = root / "originals"
        originals_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.pdf"
        (originals_dir / name).write_bytes(content)
        return f"originals/{name}"

    def _resolve_storage_path(self, storage_key: str) -> Path:
        # storage_key 必须是相对/逻辑路径，PATH 安全
        key = storage_key.replace("\\", "/")
        if key.startswith("/") or ":" in key.split("/")[0]:
            raise ContentParseError("PARSE_FAILED", "非法 storage_key")
        # 拒绝 path traversal（".." 路径段）
        if re.search(r"(^|/)\.\.(/|$)", key):
            raise ContentParseError("PARSE_FAILED", "非法 storage_key")
        return self._storage_root() / key

    # ── parse_import ──
    async def parse_import(self, batch_id: str) -> ImportBatch:
        """同步解析批次：DocumentParser + Splitter → 持久化 candidates。"""
        async with get_db_session() as db:
            batch = await db.get(ImportBatch, batch_id)
            if batch is None:
                raise ContentParseError("PARSE_FAILED", "批次不存在")
            source_doc = await db.get(SourceDocument, batch.source_document_id)
            if source_doc is None:
                raise ContentParseError("PARSE_FAILED", "来源文档不存在")
            batch.status = BATCH_PARSING
            await db.commit()
            batch_id_snapshot = batch.id
            parser_name_snapshot = batch.parser_name
            storage_path = self._resolve_storage_path(source_doc.storage_key)

        try:
            validate_pdf_page_count(storage_path)
            parsed = self._parser.parse(storage_path, parser_name_snapshot)
            splits = split_document(parsed)
            # C3：确定性答案匹配（答案区 → candidate.original_answer/original_solution）
            matches = ContentAnswerMatcher().match(parsed.blocks, splits)
            candidates = [
                self._build_candidate(sq, idx, batch_id_snapshot, matches.get(sq.identity))
                for idx, sq in enumerate(splits, start=1)
            ]
        except ContentParseError as e:
            await self._fail_batch(batch_id_snapshot, e.code, e.message)
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("解析批次异常")
            await self._fail_batch(batch_id_snapshot, "PARSE_FAILED", str(e))
            raise ContentParseError("PARSE_FAILED", f"解析失败: {e}")

        async with get_db_session() as db:
            batch = await db.get(ImportBatch, batch_id_snapshot)
            for cand in candidates:
                db.add(cand)
            batch.status = BATCH_PARSED
            batch.parser_version = parsed.parser_version
            batch.stats = {
                "total_candidates": len(candidates),
                "supported_count": sum(1 for c in candidates if c.supported),
            }
            batch.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(batch)
            return batch

    def _build_candidate(self, sq, index: int, batch_id: str, match=None) -> ContentImportCandidate:
        detected = sq.detected_question_type
        warnings = list(sq.warnings)
        original_answer = (match.original_answer if match and match.original_answer else "") or ""
        original_solution = (match.original_solution if match and match.original_solution else "") or ""
        if match is not None and match.status != MATCHED:
            for w in match.warnings:
                if w not in warnings:
                    warnings.append(w)

        stem = sq.raw_text
        supported = False
        options = None

        if detected == "choice":
            # 题干尾部答案泄漏：官方答案确认 -> 剥离泄漏字母；无法确认 -> 不发布
            if "possible_answer_leak" in warnings:
                stripped, removed = _strip_confirmed_answer_leak(stem, original_answer)
                if removed and removed == original_answer:
                    stem = stripped
                    warnings = [w for w in warnings if w != "possible_answer_leak"]
                else:
                    supported = False
            if sq.options is not None and "option_parse_uncertain" not in warnings:
                options = sq.options
                supported = True
        elif detected == "fill_candidate":
            # 依据官方原答案做第二级分类（确定性；不得强行分类）
            subtype = classify_fill_subtype(original_answer)
            detected = subtype
            if subtype == "fill":
                if "fill_type_needs_review" not in warnings:
                    warnings.append("fill_type_needs_review")
            supported = subtype in SUPPORTED_TYPES
        else:
            # calculation / proof / unknown：识别但 unsupported
            supported = detected in SUPPORTED_TYPES

        return ContentImportCandidate(
            import_batch_id=batch_id,
            candidate_index=index,
            source_page_start=sq.page_start,
            source_page_end=sq.page_end,
            source_question_number=sq.question_number,
            raw_parsed_content=sq.raw_text,
            stem=stem,
            options=options,
            original_answer=original_answer,
            original_solution=original_solution,
            detected_question_type=detected,
            supported=supported,
            warnings=warnings,
            suggested_knowledge_point_codes=[],
            status=CAND_PARSED,
        )

    async def _fail_batch(self, batch_id: str, code: str, message: str) -> None:
        async with get_db_session() as db:
            batch = await db.get(ImportBatch, batch_id)
            if batch is not None:
                batch.status = BATCH_FAILED
                batch.error_code = code
                batch.error_message = message[:2000]
                batch.completed_at = datetime.now(timezone.utc)
                await db.commit()

    # ── list_batches / get_batch ──
    async def list_batches(self, admin_user_id: str) -> List[ImportBatch]:
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(ImportBatch)
                    .where(ImportBatch.created_by == admin_user_id)
                    .order_by(ImportBatch.created_at.desc())
                )
            ).scalars().all()
            return list(rows)

    async def get_batch(self, batch_id: str) -> Optional[ImportBatch]:
        async with get_db_session() as db:
            return await db.get(ImportBatch, batch_id)

    # ── list_candidates ──
    async def list_candidates(self, batch_id: str) -> List[ContentImportCandidate]:
        async with get_db_session() as db:
            batch = await db.get(ImportBatch, batch_id)
            if batch is None:
                raise ContentParseError("PARSE_FAILED", "批次不存在")
            rows = (
                await db.execute(
                    select(ContentImportCandidate)
                    .where(ContentImportCandidate.import_batch_id == batch_id)
                    .order_by(ContentImportCandidate.candidate_index)
                )
            ).scalars().all()
            return list(rows)

    # ── update_candidate（最小编辑，不改 provenance）──
    async def update_candidate(self, batch_id: str, candidate_id: str, patch: Dict[str, Any]) -> ContentImportCandidate:
        allowed = {k: v for k, v in patch.items() if k in EDITABLE_CANDIDATE_FIELDS and v is not None}
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, candidate_id)
            if cand is None or cand.import_batch_id != batch_id:
                raise ContentParseError("PARSE_FAILED", "候选不存在")
            for k, v in allowed.items():
                setattr(cand, k, v)
            # 依据 detected_question_type 重新计算 supported
            cand.supported = (cand.detected_question_type or "") in SUPPORTED_TYPES
            cand.status = CAND_EDITED if cand.status == CAND_PARSED else cand.status
            await db.commit()
            await db.refresh(cand)
            return cand

    # ── source document / page preview（admin-only，Step 1.1-D）──
    async def get_source_document(self, document_id: str) -> Optional[SourceDocument]:
        async with get_db_session() as db:
            doc = await db.get(SourceDocument, document_id)
            return doc if doc is not None and doc.status == "active" else None

    async def render_page_preview(self, document_id: str, page: int) -> bytes:
        """渲染来源 PDF 指定页为 PNG（PyMuPDF，已进入主 runtime）。

        安全要求：
        - storage_key 必须为相对/逻辑路径（_resolve_storage_path 已防 path traversal）；
        - 页码 1-based 且必须落在 [1, page_count]；
        - 不暴露文件系统绝对路径（返回图像而非路径）。
        """
        import asyncio
        import fitz

        async with get_db_session() as db:
            doc = await db.get(SourceDocument, document_id)
        if doc is None or doc.status != "active":
            raise ContentParseError("PARSE_FAILED", "来源文档不存在")
        storage_path = self._resolve_storage_path(doc.storage_key)

        def _render() -> bytes:
            if not storage_path.exists() or not storage_path.is_file():
                raise ContentParseError("PARSE_FAILED", "来源文件缺失")
            pdf = fitz.open(str(storage_path))
            try:
                if page < 1 or page > pdf.page_count:
                    raise ContentParseError("PARSE_FAILED", f"页码越界: {page}")
                pix = pdf[page - 1].get_pixmap(dpi=110)
                return pix.tobytes("png")
            finally:
                pdf.close()

        return await asyncio.to_thread(_render)

    # ── reject candidate（unsupported / 无需保留）──
    async def reject_candidate(self, batch_id: str, candidate_id: str) -> ContentImportCandidate:
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, candidate_id)
            if cand is None or cand.import_batch_id != batch_id:
                raise ContentParseError("PARSE_FAILED", "候选不存在")
            cand.status = CAND_REJECTED
            await db.commit()
            await db.refresh(cand)
            return cand

    # ── create_drafts ──
    async def create_drafts(
        self,
        batch_id: str,
        candidate_ids: List[str],
        ai_provider: Optional[str] = None,
        is_ai_generated: bool = False,
        ai_analysis_overrides: Optional[Dict[str, Any]] = None,
        skip_supported_check: bool = False,
    ) -> Dict[str, Any]:
        """将 candidate 落为正式 Question draft（复用 QuestionImporter）。

        幂等：同一 candidate 已存在 Question 时返回既有题，不重复创建。
        不变量：仅 draft；原答案保留；provenance 保留。
        当 skip_supported_check=True（AI pipeline 调用）时，不再限制题型，
        由 AI 判断的 question_type 直接入库。
        """
        known_codes = await self._load_known_kp_codes()
        result: Dict[str, Any] = {"created": [], "skipped": [], "errors": []}

        for candidate_id in candidate_ids:
            async with get_db_session() as db:
                cand = (
                    await db.execute(
                        select(ContentImportCandidate)
                        .options(
                            selectinload(ContentImportCandidate.import_batch)
                            .selectinload(ImportBatch.source_document)
                        )
                        .where(ContentImportCandidate.id == candidate_id)
                    )
                ).scalar_one_or_none()
                if cand is None or cand.import_batch_id != batch_id:
                    result["errors"].append({"candidate_id": candidate_id, "error": "候选不存在"})
                    continue
                if not skip_supported_check and not cand.supported:
                    result["errors"].append({
                        "candidate_id": candidate_id,
                        "error": "unsupported: 仅受支持题型可转正式题",
                    })
                    continue
                # KP code 校验：必须来自现有 24 个 code
                codes = list(cand.suggested_knowledge_point_codes or [])
                unknown = [c for c in codes if c not in known_codes]
                if unknown:
                    result["errors"].append({
                        "candidate_id": candidate_id,
                        "error": f"未知知识点 code: {unknown}",
                    })
                    continue
                # 幂等：同 candidate 已落题 → 返回既有题
                existing_q = (
                    await db.execute(
                        select(Question).where(Question.source_candidate_id == candidate_id).limit(1)
                    )
                ).scalar_one_or_none()
                if existing_q is not None:
                    result["skipped"].append(existing_q.id)
                    continue

                qid = self._new_question_id()
                source_name = cand.import_batch.source_document.original_filename if cand.import_batch.source_document else ""
                question_dict = {
                    "id": qid,
                    "content": cand.stem or "",
                    "question_type": cand.detected_question_type or "text",
                    "options": cand.options or [],
                    "answer": cand.original_answer or "",
                    "analysis": cand.original_solution or "",
                    "category": (cand.import_batch.source_document.original_filename if cand.import_batch.source_document else "") or "待分类",
                    "difficulty": 3,
                    "source": source_name,
                    "review_status": "draft",
                    "is_ai_generated": False,
                    "source_candidate_id": candidate_id,
                }
                # AI enrichment 路径（Step 1.1-E2-A0）：标记 provider / is_ai_generated，
                # 并用 AI 结构化字段覆盖（原答案仍为 ground truth，不被 AI 覆盖）。
                if ai_provider:
                    question_dict["ai_provider"] = ai_provider
                    question_dict["is_ai_generated"] = is_ai_generated
                    overrides = ai_analysis_overrides or {}
                    if overrides.get("analysis") is not None:
                        question_dict["analysis"] = overrides["analysis"]
                    if overrides.get("difficulty") is not None:
                        question_dict["difficulty"] = overrides["difficulty"]
                    if overrides.get("answer_spec") is not None:
                        question_dict["answer_spec"] = overrides["answer_spec"]
                    if overrides.get("common_mistakes") is not None:
                        question_dict["common_mistakes"] = overrides["common_mistakes"]
                    ov_kp = overrides.get("knowledge_point_codes")
                    if ov_kp:
                        codes = list(ov_kp)
                if codes:
                    question_dict["course_code"] = COURSE_CODE
                    question_dict["knowledge_point_codes"] = codes

            import_result = await self._importer.import_from_dict_list([question_dict])
            if import_result.failed:
                result["errors"].append({
                    "candidate_id": candidate_id,
                    "error": (import_result.errors[0] if import_result.errors else "导入失败"),
                })
                continue
            # 标记 candidate 为 imported
            async with get_db_session() as db:
                cand = await db.get(ContentImportCandidate, candidate_id)
                if cand is not None:
                    cand.status = CAND_IMPORTED
                    await db.commit()
            result["created"].append(qid)

        return result

    @staticmethod
    def _new_question_id() -> str:
        # Question.id 为 String(20)：CI + 16 hex = 18 字符，合法
        return "CI" + uuid.uuid4().hex[:16]

    async def _load_known_kp_codes(self) -> set:
        from app.data.models import KnowledgePoint
        async with get_db_session() as db:
            codes = (
                await db.execute(select(KnowledgePoint.code))
            ).scalars().all()
            return set(codes)


# 轻量单例（供 API 复用）
_service: Optional[ContentImportService] = None


def get_content_import_service() -> ContentImportService:
    global _service
    if _service is None:
        _service = ContentImportService()
    return _service