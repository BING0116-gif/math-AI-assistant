"""
Step 1.1-D content review tests.

Covers:
- SourceDocument page preview API (admin 200 / student 403 / invalid page / storage traversal / missing file)
- KnowledgePoint catalog
- Question review state machine (draft → reviewed → published)
- Validation: invalid answer / no KP / unsupported type / blocking warning
- Publish: reviewed → published; draft → rejected; edited reviewed → back to draft
- published-only query (draft/reviewed 不进入正式题池)
- Provenance: review/edit 不修改 candidate raw provenance
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import fitz  # PyMuPDF
import uuid
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base,
    ContentImportCandidate,
    ImportBatch,
    Question,
    SourceDocument,
)
from app.services.content_import import ContentImportService, ContentParseError
from app.services.content_review import ContentReviewError, ContentReviewService
from app.services.content_stats import ContentStatsService
from app.services.document_parser import MODE_QUICK
from app.services.knowledge_seed import seed_phase_one_calculus


# ── fixtures（复用 test_content_ingestion 的模式）──
@pytest.fixture
def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(eng.sync_engine, "connect")
    def _fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
    return eng


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def patch_global_session_factory(session_factory, monkeypatch):
    import app.data.database as db
    monkeypatch.setattr(db, "async_session_factory", session_factory)
    yield session_factory


@pytest.fixture
def patch_storage_root(tmp_path, monkeypatch):
    from app.config.settings import settings
    root = tmp_path / "runtime" / "content"
    monkeypatch.setattr(settings, "CONTENT_STORAGE_ROOT", str(root))
    return root


@pytest.fixture
def service(patch_global_session_factory, patch_storage_root):
    return ContentImportService()


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontname="china-s", encoding="gbk")
    data = doc.tobytes()
    doc.close()
    return data


MIXED_PDF_TEXT = (
    "高等数学自测\n"
    "一、单项选择题\n"
    "1. 设函数 f(x)=x^2，则 f'(1) 等于（ ）。\n"
    "A. 1\n"
    "B. 2\n"
    "C. 3\n"
    "D. 4\n"
    "二、证明题\n"
    "1. 证明函数 f(x)=x 在 [0,1] 上连续。\n"
)


async def seed_kps():
    from app.data.database import get_db_session
    async with get_db_session() as db:
        await seed_phase_one_calculus(db)
        await db.commit()


async def first_kp_code() -> str:
    from app.data.database import get_db_session
    from app.data.models import KnowledgePoint
    async with get_db_session() as db:
        kp = (await db.execute(select(KnowledgePoint).limit(1))).scalar_one()
        return kp.code


async def create_parsed_batch(service, text=MIXED_PDF_TEXT):
    batch, created = await service.create_import(
        admin_user_id="admin-1",
        original_filename="test.pdf",
        content=make_pdf(text),
        mode=MODE_QUICK,
    )
    assert created is True
    batch = await service.parse_import(batch.id)
    assert batch.status == "parsed", batch.error_message
    candidates = await service.list_candidates(batch.id)
    return batch, candidates


async def make_reviewable_choice_draft(service):
    """完整搭建一条可审核的 choice draft：batch → candidate → answer/solution/KP → draft。"""
    batch, candidates = await create_parsed_batch(service)
    choice = next(c for c in candidates if c.detected_question_type == "choice")
    code = await first_kp_code()
    choice = await service.update_candidate(
        batch_id=choice.import_batch_id,
        candidate_id=choice.id,
        patch={
            "original_answer": "B",
            "original_solution": "f'(x)=2x，故 f'(1)=2。",
            "suggested_knowledge_point_codes": [code],
        },
    )
    result = await service.create_drafts(choice.import_batch_id, [choice.id])
    assert len(result["created"]) == 1
    return batch, choice, result["created"][0]


async def _inject_unknown_candidate(batch_id: str) -> str:
    """直接构造一个真正 unsupported 的候选（unknown 不在 SUPPORTED_TYPES）。

    用于验证发布网关仍拦截未知题型，而不依赖 MIXED 文本里恰好有 unsupported 题型。
    """
    from app.data.database import get_db_session

    cid = "CI" + uuid.uuid4().hex[:16]
    async with get_db_session() as db:
        db.add(ContentImportCandidate(
            id=cid,
            import_batch_id=batch_id,
            candidate_index=99,
            source_page_start=1,
            source_page_end=1,
            source_question_number="99",
            stem="无法识别的题型",
            options=None,
            original_answer="?",
            original_solution="",
            detected_question_type="unknown",
            supported=False,
            suggested_knowledge_point_codes=[],
            status="parsed",
        ))
        await db.commit()
    return cid


# ══════════════════════════════════════════════════════════════════
# Preview API
# ══════════════════════════════════════════════════════════════════
class TestPreviewAPI:
    pytestmark = pytest.mark.asyncio

    async def test_admin_render_page_png(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        batch, _ = await create_parsed_batch(service)
        doc_id = batch.source_document_id
        png = await service.render_page_preview(doc_id, 1)
        assert png.startswith(b"\x89PNG")

    async def test_invalid_page_out_of_range(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        batch, _ = await create_parsed_batch(service)
        with pytest.raises(ContentParseError):
            await service.render_page_preview(batch.source_document_id, 999)
        with pytest.raises(ContentParseError):
            await service.render_page_preview(batch.source_document_id, 0)

    async def test_missing_source_document(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        with pytest.raises(ContentParseError):
            await service.render_page_preview("no-such-doc", 1)

    async def test_storage_traversal_rejected(self, service, engine):
        """storage_key 含 .. 必须被拒绝（防 path traversal）。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    SourceDocument.__table__.insert().values(
                        id="traversal-doc",
                        original_filename="evil.pdf",
                        storage_key="../evil.pdf",
                        sha256="deadbeef" * 8,
                        mime_type="application/pdf",
                        size_bytes=1,
                        created_by="admin-1",
                        status="active",
                    )
                )
            )
        with pytest.raises(ContentParseError):
            await service.render_page_preview("traversal-doc", 1)

    async def test_missing_file(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    SourceDocument.__table__.insert().values(
                        id="missing-file-doc",
                        original_filename="ghost.pdf",
                        storage_key="originals/ghost.pdf",
                        sha256="deadbeef" * 8,
                        mime_type="application/pdf",
                        size_bytes=1,
                        created_by="admin-1",
                        status="active",
                    )
                )
            )
        with pytest.raises(ContentParseError):
            await service.render_page_preview("missing-file-doc", 1)

    async def test_student_403(self, patch_global_session_factory):
        from app.api.content_import_api import preview_source_page
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await preview_source_page(
                SimpleNamespace(state=SimpleNamespace(current_user=SimpleNamespace(id="stu", role="student"))),
                id="doc-1",
                page=1,
            )
        assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════
# KnowledgePoint catalog
# ══════════════════════════════════════════════════════════════════
class TestKPCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_catalog_from_published_version(self, engine, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        svc = ContentReviewService()
        catalog = await svc.get_knowledge_point_catalog()
        assert len(catalog) >= 1
        first = catalog[0]
        assert "code" in first and "name" in first and "chapter" in first


# ══════════════════════════════════════════════════════════════════
# Question review state machine
# ══════════════════════════════════════════════════════════════════
class TestReviewStateMachine:
    pytestmark = pytest.mark.asyncio

    async def test_draft_to_reviewed(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        # 补 answer_spec（choice 契约）
        q = await svc.update_question(
            qid,
            {"answer_spec": {"version": 1, "kind": "choice", "correct": "B"}},
        )
        assert q.review_status == "draft"
        reviewed = await svc.mark_reviewed(qid)
        assert reviewed.review_status == "reviewed"

    async def test_invalid_answer_blocked(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        # 答案改成不在选项中的值
        await svc.update_question(qid, {"answer": "Z"})
        with pytest.raises(ContentReviewError) as exc:
            await svc.mark_reviewed(qid)
        assert exc.value.code == "VALIDATION_FAILED"
        assert any("答案" in e or "answer" in e for e in exc.value.errors)

    async def test_no_kp_blocked(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        await svc.update_question(qid, {"knowledge_point_codes": []})
        with pytest.raises(ContentReviewError) as exc:
            await svc.mark_reviewed(qid)
        assert any("知识点" in e for e in exc.value.errors)

    async def test_unsupported_type_blocked(self, service, engine):
        """真正 unsupported 的题型（unknown）仍被发布网关拦截，无法落题。

        注意：proof/calculation/short_answer 已纳入 SUPPORTED_TYPES（见下方
        test_proof_type_now_supported_and_draftable），故改用 unknown 验证网关不变量。
        """
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        batch, _ = await create_parsed_batch(service)
        cid = await _inject_unknown_candidate(batch.id)
        result = await service.create_drafts(batch.id, [cid])
        assert result["created"] == []  # unsupported 无法落题

    async def test_proof_type_now_supported_and_draftable(self, service, engine):
        """Step 1.1-E2 产品变更：证明题现已受支持，可直接落为 draft。

        依据用户需求（分析并入库每一道被切分的题），proof/calculation/
        short_answer 已纳入 SUPPORTED_TYPES，不再被拦在发布网关外。
        """
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        batch, candidates = await create_parsed_batch(service)
        proof = next(c for c in candidates if c.detected_question_type == "proof")
        assert proof.supported is True  # 产品变更断言
        result = await service.create_drafts(proof.import_batch_id, [proof.id])
        # create_drafts 返回新落题的 Question id（CI 前缀），证明题现已可落题
        assert len(result["created"]) == 1
        assert result["created"][0].startswith("CI")

    async def test_choice_answer_spec_mismatch_blocked(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        # answer=B 但 answer_spec 说 A → 不一致
        await svc.update_question(
            qid,
            {"answer_spec": {"version": 1, "kind": "choice", "correct": "A"}},
        )
        with pytest.raises(ContentReviewError) as exc:
            await svc.mark_reviewed(qid)
        assert any("不一致" in e for e in exc.value.errors)

    async def test_blocking_warning_blocked_then_resolved(self, service, engine):
        """阻塞警告阻止 reviewed；内容修正后重新校验通过（不删除 provenance）。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        # 手工构造带 option_parse_uncertain 的 candidate + 空 options 的 draft
        from app.data.database import get_db_session
        code = await first_kp_code()
        async with get_db_session() as db:
            src = SourceDocument(
                id="sd-block",
                original_filename="block.pdf",
                storage_key="originals/block.pdf",
                sha256="deadbeef" * 8,
                mime_type="application/pdf",
                size_bytes=1,
                created_by="admin-1",
                status="active",
            )
            db.add(src)
            batch = ImportBatch(
                id="b-block",
                source_document_id="sd-block",
                status="parsed",
                parser_name=MODE_QUICK,
                parser_version="test",
                created_by="admin-1",
                stats={"candidate_count": 1},
            )
            db.add(batch)
            cand = ContentImportCandidate(
                id="c-block",
                import_batch_id="b-block",
                candidate_index=1,
                source_page_start=1,
                source_page_end=1,
                source_question_number="1",
                stem="题干",
                options=[],
                original_answer="B",
                original_solution="解析",
                detected_question_type="choice",
                supported=False,
                warnings=["option_parse_uncertain"],
                raw_parsed_content="raw original",
            )
            db.add(cand)
            await db.commit()

        from app.services.question_importer import QuestionImporter
        importer = QuestionImporter()
        r = await importer.import_from_dict_list([
            {
                "id": "Q-BLOCK",
                "category": "高数",
                "content": "题干",
                "question_type": "choice",
                "options": [],
                "answer": "B",
                "analysis": "解析",
                "knowledge_point_codes": [code],
                "course_code": None,
                "source_candidate_id": "c-block",
            }
        ])
        assert r.success == 1

        svc = ContentReviewService()
        await svc.update_question(
            "Q-BLOCK",
            {"answer_spec": {"version": 1, "kind": "choice", "correct": "B"}},
        )
        with pytest.raises(ContentReviewError) as exc:
            await svc.mark_reviewed("Q-BLOCK")
        assert any("阻塞" in e or "option_parse_uncertain" in e for e in exc.value.errors)

        # 人工补全选项 → warning 依据当前内容重新校验不再阻塞
        await svc.update_question(
            "Q-BLOCK",
            {"options": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}]},
        )
        reviewed = await svc.mark_reviewed("Q-BLOCK")
        assert reviewed.review_status == "reviewed"

        # provenance 未被修改
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, "c-block")
            assert cand.raw_parsed_content == "raw original"
            assert cand.warnings == ["option_parse_uncertain"]


# ══════════════════════════════════════════════════════════════════
# Publish
# ══════════════════════════════════════════════════════════════════
class TestPublish:
    pytestmark = pytest.mark.asyncio

    async def _to_reviewed(self, service):
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        await svc.update_question(qid, {"answer_spec": {"version": 1, "kind": "choice", "correct": "B"}})
        await svc.mark_reviewed(qid)
        return svc, qid

    async def test_reviewed_to_published(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        svc, qid = await self._to_reviewed(service)
        pub = await svc.publish(qid)
        assert pub.review_status == "published"

    async def test_draft_publish_rejected(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        with pytest.raises(ContentReviewError) as exc:
            await svc.publish(qid)
        assert exc.value.code == "STATE"

    async def test_edited_reviewed_requires_rereview(self, service, engine):
        """reviewed 后关键内容修改 → 自动回 draft，不能直接 published。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        svc, qid = await self._to_reviewed(service)
        # 修改 answer（关键字段）
        q = await svc.update_question(qid, {"answer": "A"})
        assert q.review_status == "draft"  # 自动回 draft
        with pytest.raises(ContentReviewError) as exc:
            await svc.publish(qid)
        assert exc.value.code == "STATE"

    async def test_reviewed_content_edit_without_key_field_stays_reviewed(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        svc, qid = await self._to_reviewed(service)
        # 非关键字段（estimated_time）修改不影响状态
        q = await svc.update_question(qid, {"estimated_time": 6})
        assert q.review_status == "reviewed"

    async def test_published_only_query(self, service, engine):
        """published 进入 published-only 查询；draft/reviewed 不进入。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        svc, qid = await self._to_reviewed(service)
        svc2, qid2 = await self._to_reviewed(service)
        await svc.publish(qid)

        published = await svc.list_questions("published")
        published_ids = {q.id for q in published}
        assert qid in published_ids
        assert qid2 not in published_ids  # reviewed 不进正式题池

        drafts = await svc.list_questions("draft")
        assert qid not in {q.id for q in drafts}
        reviewed = await svc.list_questions("reviewed")
        assert qid not in {q.id for q in reviewed}


# ══════════════════════════════════════════════════════════════════
# Provenance
# ══════════════════════════════════════════════════════════════════
class TestProvenance:
    pytestmark = pytest.mark.asyncio

    async def test_edit_and_review_keep_candidate_provenance(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        batch, choice, qid = await make_reviewable_choice_draft(service)

        from app.data.database import get_db_session
        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, choice.id)
            raw_before = cand.raw_parsed_content
            answer_before = cand.original_answer
            solution_before = cand.original_solution

        svc = ContentReviewService()
        await svc.update_question(
            qid,
            {
                "content": "人工修改后的题干（不覆盖 provenance）",
                "answer_spec": {"version": 1, "kind": "choice", "correct": "B"},
            },
        )
        await svc.mark_reviewed(qid)

        async with get_db_session() as db:
            cand = await db.get(ContentImportCandidate, choice.id)
            assert cand.raw_parsed_content == raw_before
            assert cand.original_answer == answer_before
            assert cand.original_solution == solution_before

    async def test_edit_question_cannot_touch_provenance_fields(self, service, engine):
        """PATCH questions 白名单禁止编辑 provenance（通过 service 白名单过滤）。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        _, _, qid = await make_reviewable_choice_draft(service)
        svc = ContentReviewService()
        # 尝试编辑 provenance 字段（应被白名单过滤，不影响结果）
        q = await svc.update_question(
            qid,
            {
                "raw_parsed_content": "hacked",
                "source": "hacked",
                "content": "正常题干",
                "answer_spec": {"version": 1, "kind": "choice", "correct": "B"},
            },
        )
        assert q.content == "正常题干"
        assert q.source != "hacked"


# ══════════════════════════════════════════════════════════════════
# AI Offline：Import → Preview → Edit → Draft → Reviewed → Published
# ══════════════════════════════════════════════════════════════════
class TestAIOfflineFullChain:
    """Step 1.1-D §47：整个审核闭环必须在 AI_ENABLED=false 下可用。

    内容导入/审核服务（content_import / content_review）本身不依赖 AI，
    本测试用 monkeypatch 强制 AI_ENABLED=false 走完完整链路验证：
    Import → Preview → Edit → Draft → Reviewed → Published。
    """

    pytestmark = pytest.mark.asyncio

    async def test_full_chain_with_ai_disabled(
        self, service, engine, monkeypatch
    ):
        monkeypatch.setenv("AI_ENABLED", "false")
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()

        # Import（PDF 上传 + quick 解析）
        batch, created = await service.create_import(
            admin_user_id="admin-1",
            original_filename="offline-test.pdf",
            content=make_pdf(MIXED_PDF_TEXT),
            mode=MODE_QUICK,
        )
        assert created is True
        batch = await service.parse_import(batch.id)
        assert batch.status == "parsed", batch.error_message

        # Preview（渲染来源 PDF 页）
        png = await service.render_page_preview(batch.source_document_id, 1)
        assert png.startswith(b"\x89PNG")

        # Edit candidate（补 answer/solution/KP）
        candidates = await service.list_candidates(batch.id)
        choice = next(c for c in candidates if c.detected_question_type == "choice")
        code = await first_kp_code()
        choice = await service.update_candidate(
            batch_id=choice.import_batch_id,
            candidate_id=choice.id,
            patch={
                "original_answer": "B",
                "original_solution": "f'(x)=2x，故 f'(1)=2。",
                "suggested_knowledge_point_codes": [code],
            },
        )
        assert choice.original_answer == "B"

        # Draft（幂等：重复创建不新增）
        result = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert len(result["created"]) == 1
        qid = result["created"][0]
        result2 = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert result2["created"] == []  # 幂等，重复创建不新增

        # Reviewed（服务端校验）
        svc = ContentReviewService()
        await svc.update_question(
            qid, {"answer_spec": {"version": 1, "kind": "choice", "correct": "B"}}
        )
        reviewed = await svc.mark_reviewed(qid)
        assert reviewed.review_status == "reviewed"

        # Published
        pub = await svc.publish(qid)
        assert pub.review_status == "published"

        # published-only：仅 published 进入正式题池
        published_ids = {q.id for q in await svc.list_questions("published")}
        assert qid in published_ids
        draft_ids = {q.id for q in await svc.list_questions("draft")}
        reviewed_ids = {q.id for q in await svc.list_questions("reviewed")}
        assert qid not in draft_ids
        assert qid not in reviewed_ids


# ══════════════════════════════════════════════════════════════════
# Content Stats / Coverage（Step 1.1-E1，只读）
# ══════════════════════════════════════════════════════════════════
class TestContentStats:
    pytestmark = pytest.mark.asyncio

    async def _import_q(
        self, qid: str, kp_code: str, review_status: str = "draft", qtype: str = "choice"
    ) -> None:
        from app.services.question_importer import QuestionImporter
        importer = QuestionImporter()
        r = await importer.import_from_dict_list([
            {
                "id": qid,
                "category": "高数",
                "content": f"题干 {qid}",
                "question_type": qtype,
                "options": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
                "answer": "B",
                "analysis": "解析",
                "knowledge_point_codes": [kp_code] if kp_code else [],
                "course_code": None,
                "review_status": review_status,
                "source_candidate_id": None,
            }
        ], trusted=True)
        assert r.success == 1

    async def test_question_status_counts(self, service, engine):
        """published / draft / reviewed / retired 计数正确，且明确区分。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        code = await first_kp_code()
        await self._import_q("Q-S-1", code, "draft")
        await self._import_q("Q-S-2", code, "reviewed")
        await self._import_q("Q-S-3", code, "published")
        await self._import_q("Q-S-4", code, "retired")
        svc = ContentStatsService()
        counts = await svc.question_status_counts()
        assert counts["total"] == 4
        assert counts["draft"] == 1
        assert counts["reviewed"] == 1
        assert counts["published"] == 1
        assert counts["retired"] == 1

    async def test_candidate_not_counted_as_question(self, service, engine):
        """candidate staging 不进入正式 Question 数量。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        batch, candidates = await create_parsed_batch(service)
        assert len(candidates) >= 1
        svc = ContentStatsService()
        counts = await svc.question_status_counts()
        assert counts["total"] == 0  # candidate 不算正式题
        staging = await svc.candidate_staging_counts()
        assert staging["total"] == len(candidates)

    async def test_kp_coverage_m2n_counts_and_empty_included(self, service, engine):
        """question_knowledge_points 规范 M:N 统计；无题 KP 含 0 且列入。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        from app.data.database import get_db_session
        from app.data.models import KnowledgePoint
        async with get_db_session() as db:
            kps = (await db.execute(select(KnowledgePoint).order_by(KnowledgePoint.code).limit(3))).scalars().all()
        kp_a, kp_b, kp_c = [k.code for k in kps]

        # kp_a: 1 draft + 2 published
        await self._import_q("Q-K-1", kp_a, "draft")
        await self._import_q("Q-K-2", kp_a, "published")
        await self._import_q("Q-K-3", kp_a, "published")
        # kp_b: 1 reviewed
        await self._import_q("Q-K-4", kp_b, "reviewed")
        # kp_c: 无题

        svc = ContentStatsService()
        items = await svc.kp_coverage()
        by_code = {it["code"]: it for it in items}
        assert len(items) == 24  # 全部 24 KP 都在
        assert by_code[kp_a]["draft"] == 1
        assert by_code[kp_a]["published"] == 2
        assert by_code[kp_a]["status"] == "CRITICAL"  # 1-2 published
        assert by_code[kp_b]["reviewed"] == 1
        assert by_code[kp_b]["published"] == 0
        assert by_code[kp_b]["status"] == "EMPTY"
        assert by_code[kp_c]["draft"] == 0 and by_code[kp_c]["published"] == 0
        assert by_code[kp_c]["status"] == "EMPTY"

    async def test_gap_remaining_uses_published_only(self, service, engine):
        """target 计数只看 published；draft/reviewed 不计入。"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        code = await first_kp_code()
        await self._import_q("Q-G-1", code, "published")
        await self._import_q("Q-G-2", code, "draft")
        await self._import_q("Q-G-3", code, "reviewed")
        svc = ContentStatsService()
        gap = await svc.gap_report()
        assert gap["target"] == 100
        assert gap["published"] == 1
        assert gap["remaining"] == 99  # draft/reviewed 不计入 target

    async def test_unsupported_candidate_not_counted_toward_target(self, service, engine):
        """unsupported candidate 不计入 published target（只在 staging 单独统计）。

        注意：proof 现已受支持，故注入一个真正 unknown 的候选来验证 staging 单独统计。
        """
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        batch, candidates = await create_parsed_batch(service)
        await _inject_unknown_candidate(batch.id)
        svc = ContentStatsService()
        staging = await svc.candidate_staging_counts()
        assert staging["total"] == len(candidates) + 1
        unsupported = staging["unsupported"]
        assert unsupported >= 1  # unknown 题型在 staging 中单独统计
        gap = await svc.gap_report()
        # candidate staging 与 published target 完全无关
        assert gap["published"] == 0
        assert gap["remaining"] == 100
        assert gap["remaining"] == 100 - gap["published"]

    # ── API 权限：student 403 / admin 200 ──
    async def test_stats_student_403(self, patch_global_session_factory):
        from app.api.content_import_api import content_stats
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await content_stats(
                SimpleNamespace(state=SimpleNamespace(current_user=SimpleNamespace(id="stu", role="student")))
            )
        assert exc.value.status_code == 403

    async def test_coverage_student_403(self, patch_global_session_factory):
        from app.api.content_import_api import content_coverage
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await content_coverage(
                SimpleNamespace(state=SimpleNamespace(current_user=SimpleNamespace(id="stu", role="student")))
            )
        assert exc.value.status_code == 403

    async def test_stats_admin_200(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        from app.api.content_import_api import content_stats
        resp = await content_stats(
            SimpleNamespace(state=SimpleNamespace(current_user=SimpleNamespace(id="admin-1", role="admin")))
        )
        assert resp.code == 0
        assert resp.data.question_status["published"] == 0
        payload = resp.data.model_dump()
        assert "candidates" in payload and "gap" in payload

    async def test_coverage_admin_200(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_kps()
        from app.api.content_import_api import content_coverage
        resp = await content_coverage(
            SimpleNamespace(state=SimpleNamespace(current_user=SimpleNamespace(id="admin-1", role="admin")))
        )
        assert resp.code == 0
        assert resp.data.target == 100
        assert resp.data.published == 0
        assert resp.data.remaining == 100
        assert len(resp.data.kps) == 24
        assert resp.data.kp_status_counts["EMPTY"] == 24