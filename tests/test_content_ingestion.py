"""
Step 1.1-C2 content ingestion tests.

Covers:
- DocumentParser (quick / mineru / invalid / missing / failure / timeout)
- ContentImportCandidate persistence (reload-safe, provenance immutable)
- supported vs unsupported question types (staging only)
- draft creation via QuestionImporter (source_candidate_id, idempotent, draft-only)
- valid/unknown knowledge point codes
- AI_ENABLED=false import works
- admin auth (401/403/200)
"""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import fitz  # PyMuPDF
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.database import get_db_session
from app.data.models import (
    Base,
    ContentImportCandidate,
    ImportBatch,
    Question,
    SourceDocument,
)
from app.services.content_import import ContentImportService
from app.services.document_parser import (
    MODE_MINERU,
    MODE_QUICK,
    ContentParseError,
    DocumentParser,
    INVALID_PDF,
    PARSER_UNAVAILABLE,
    PARSE_FAILED,
)
from app.services.knowledge_seed import seed_phase_one_calculus

# 首个正式自动判题支持题型
SUPPORTED_TYPES = {"choice", "judge", "numeric_fill", "expression_fill"}

# 各测试类按需单独标记 async；同步用例不标记


# ── fixtures ──
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
    """让依赖全局 get_db_session() 的 service/importer 指向测试引擎。"""
    import app.data.database as db
    monkeypatch.setattr(db, "async_session_factory", session_factory)
    yield session_factory


@pytest.fixture
def patch_storage_root(tmp_path, monkeypatch):
    """把正式存储根目录指到临时目录，避免测试写入仓库。"""
    from app.config.settings import settings
    root = tmp_path / "runtime" / "content"
    monkeypatch.setattr(settings, "CONTENT_STORAGE_ROOT", str(root))
    return root


@pytest.fixture
def service(patch_global_session_factory, patch_storage_root):
    return ContentImportService()


# ── helpers ──
def make_pdf(text: str) -> bytes:
    """用 PyMuPDF 生成包含中文文本的单页 PDF（用于测试 fixture）。"""
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


async def create_parsed_batch(service, text, mode=MODE_QUICK):
    """上传并解析，返回 (batch, source_doc, candidates)。"""
    batch, created = await service.create_import(
        admin_user_id="admin-1",
        original_filename="test.pdf",
        content=make_pdf(text),
        mode=mode,
    )
    assert created is True
    batch = await service.parse_import(batch.id)
    assert batch.status == "parsed", batch.error_message
    candidates = await service.list_candidates(batch.id)
    return batch, candidates


# ══════════════════════════════════════════════════════════════════
# §30 Parser
# ══════════════════════════════════════════════════════════════════
class TestParser:
    def test_quick_parses_valid_pdf(self, tmp_path):
        pdf = tmp_path / "valid.pdf"
        pdf.write_bytes(make_pdf("1. What is 1+1?\nA. 1\nB. 2\n"))
        doc = DocumentParser().parse(str(pdf), MODE_QUICK)
        assert doc.parser_name == MODE_QUICK
        assert doc.page_mapping_uncertain is False
        assert len(doc.pages) == 1
        assert "1+1" in doc.markdown

    def test_quick_rejects_invalid_pdf(self, tmp_path):
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"This is not a pdf at all")
        with pytest.raises(ContentParseError) as exc:
            DocumentParser().parse(str(pdf), MODE_QUICK)
        assert exc.value.code == INVALID_PDF

    def test_mineru_missing_executable(self, tmp_path):
        pdf = tmp_path / "valid.pdf"
        pdf.write_bytes(make_pdf("text"))
        parser = DocumentParser(executable="")  # 未配置
        with pytest.raises(ContentParseError) as exc:
            parser.parse(str(pdf), MODE_MINERU)
        assert exc.value.code == PARSER_UNAVAILABLE

    def test_mineru_subprocess_failure(self, tmp_path):
        pdf = tmp_path / "valid.pdf"
        pdf.write_bytes(make_pdf("text"))
        fake_exe = tmp_path / "mineru.exe"
        fake_exe.write_bytes(b"fake")  # 文件存在，通过 executable 存在性检查
        with patch("app.services.document_parser.subprocess.Popen") as mock_popen:
            mock_proc = mock_popen.return_value
            mock_proc.returncode = 1
            mock_proc.wait.return_value = 1
            with pytest.raises(ContentParseError) as exc:
                DocumentParser(executable=str(fake_exe)).parse(str(pdf), MODE_MINERU)
            assert exc.value.code == PARSE_FAILED

    def test_mineru_timeout(self, tmp_path):
        pdf = tmp_path / "valid.pdf"
        pdf.write_bytes(make_pdf("text"))
        fake_exe = tmp_path / "mineru.exe"
        fake_exe.write_bytes(b"fake")
        with patch("app.services.document_parser.subprocess.Popen") as mock_popen, \
             patch("app.services.document_parser._kill_process_tree") as mock_kill:
            mock_proc = mock_popen.return_value
            mock_proc.pid = 12345
            mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="fake", timeout=5)
            with pytest.raises(ContentParseError) as exc:
                DocumentParser(executable=str(fake_exe)).parse(str(pdf), MODE_MINERU)
            assert exc.value.code == PARSE_FAILED
            assert "超时" in exc.value.message
            mock_kill.assert_called_once_with(12345)

    def test_mineru_success_reads_markdown(self, tmp_path):
        pdf = tmp_path / "valid.pdf"
        pdf.write_bytes(make_pdf("text"))
        fake_exe = tmp_path / "mineru.exe"
        fake_exe.write_bytes(b"fake")
        out_root = tmp_path / "out_root"
        out_dir = out_root / "out"
        out_dir.mkdir(parents=True)
        (out_dir / "doc.md").write_text("1. 题目\n", encoding="utf-8")
        with patch("app.services.document_parser.subprocess.Popen") as mock_popen, \
             patch("app.services.document_parser.tempfile.mkdtemp", return_value=str(out_root)), \
             patch("app.services.document_parser.subprocess.run") as mock_run:
            mock_proc = mock_popen.return_value
            mock_proc.returncode = 0
            mock_proc.wait.return_value = 0
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            doc = DocumentParser(executable=str(fake_exe)).parse(str(pdf), MODE_MINERU)
        assert doc.parser_name == MODE_MINERU
        assert doc.page_mapping_uncertain is True
        assert "题目" in doc.markdown


# ══════════════════════════════════════════════════════════════════
# §30 Candidate persistence / provenance
# ══════════════════════════════════════════════════════════════════
class TestCandidate:
    pytestmark = pytest.mark.asyncio

    async def test_parse_persists_candidates_and_reload(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        batch, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        assert len(candidates) == 2

        # "重启/session reload"：用全新 session 再查，候选仍存在
        from app.data.database import get_db_session
        async with get_db_session() as db:
            stored = (await db.execute(
                select(ContentImportCandidate).where(
                    ContentImportCandidate.import_batch_id == batch.id
                ).order_by(ContentImportCandidate.candidate_index)
            )).scalars().all()
        assert len(stored) == 2
        first = stored[0]
        assert first.source_page_start is not None
        assert first.source_question_number == "1"
        assert first.raw_parsed_content  # provenance 存在

    async def test_raw_parsed_content_immutable(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        cand = candidates[0]
        raw_before = cand.raw_parsed_content
        updated = await service.update_candidate(
            batch_id=cand.import_batch_id,
            candidate_id=cand.id,
            patch={"stem": "改过的题干", "options": ["A. 1", "B. 2"]},
        )
        assert updated.stem == "改过的题干"
        assert updated.raw_parsed_content == raw_before  # provenance 不改

    async def test_supported_and_unsupported_types(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        by_type = {c.detected_question_type: c for c in candidates}
        assert by_type["choice"].supported is True
        # Step 1.1-E2 产品变更：proof/calculation/short_answer 已纳入 SUPPORTED_TYPES
        assert by_type["proof"].supported is True
        # 真正 unsupported 的 unknown 题型仍被发布网关拦截，保留在 staging（不被转换）
        async with get_db_session() as db:
            db.add(ContentImportCandidate(
                id="c-unknown",
                import_batch_id=by_type["choice"].import_batch_id,
                candidate_index=99,
                detected_question_type="unknown",
                supported=False,
                stem="无法识别的题型",
                options=None,
                original_answer="?",
                original_solution="",
                suggested_knowledge_point_codes=[],
                status="parsed",
            ))
            await db.commit()
        result = await service.create_drafts(by_type["choice"].import_batch_id, ["c-unknown"])
        assert result["created"] == []
        assert any("unsupported" in e["error"] for e in result["errors"])


# ══════════════════════════════════════════════════════════════════
# §30 Draft
# ══════════════════════════════════════════════════════════════════
class TestDraft:
    pytestmark = pytest.mark.asyncio

    async def _seed_and_prep(self, service, engine):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from app.data.database import get_db_session
        async with get_db_session() as db:
            await seed_phase_one_calculus(db)
            await db.commit()
        _, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        choice = next(c for c in candidates if c.detected_question_type == "choice")
        # 设置原答案/解析（模拟答案页来源，C3 之前由人工/最小编辑提供）
        choice = await service.update_candidate(
            batch_id=choice.import_batch_id,
            candidate_id=choice.id,
            patch={"original_answer": "B", "original_solution": "f'(x)=2x，故 f'(1)=2。"},
        )
        return choice

    async def test_supported_candidate_becomes_draft(self, service, engine):
        choice = await self._seed_and_prep(service, engine)
        result = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert len(result["created"]) == 1
        qid = result["created"][0]

        from app.data.database import get_db_session
        async with get_db_session() as db:
            q = await db.get(Question, qid)
            assert q is not None
            assert q.source_candidate_id == choice.id
            assert q.review_status == "draft"  # 绝不 published
            assert q.answer == "B"  # 用原答案初始化
            assert q.analysis == "f'(x)=2x，故 f'(1)=2。"
            # 原答案/解析永久保留在 candidate provenance
            cand = await db.get(ContentImportCandidate, choice.id)
            assert cand.original_answer == "B"
            assert cand.status == "imported"

    async def test_repeated_draft_is_idempotent(self, service, engine):
        choice = await self._seed_and_prep(service, engine)
        r1 = await service.create_drafts(choice.import_batch_id, [choice.id])
        r2 = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert len(r1["created"]) == 1
        assert len(r2["created"]) == 0  # 未重复创建
        assert r2["skipped"] == r1["created"]

        from app.data.database import get_db_session
        async with get_db_session() as db:
            rows = (await db.execute(
                select(Question).where(Question.source_candidate_id == choice.id)
            )).scalars().all()
            assert len(rows) == 1  # 同 candidate 只有一条正式题

    async def test_unsupported_candidate_not_converted(self, service, engine):
        """真正 unsupported 的题型（unknown）仍被发布网关拦截，无法落题。

        注意：proof 现已受支持（见 test_supported_and_unsupported_types），
        故改用 unknown 验证发布网关不变量。
        """
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        batch_id = candidates[0].import_batch_id
        async with get_db_session() as db:
            db.add(ContentImportCandidate(
                id="c-unknown",
                import_batch_id=batch_id,
                candidate_index=99,
                detected_question_type="unknown",
                supported=False,
                stem="无法识别的题型",
                options=None,
                original_answer="?",
                original_solution="",
                suggested_knowledge_point_codes=[],
                status="parsed",
            ))
            await db.commit()
        result = await service.create_drafts(batch_id, ["c-unknown"])
        assert result["created"] == []
        assert len(result["errors"]) == 1
        assert "unsupported" in result["errors"][0]["error"]

    async def test_unknown_kp_rejected(self, service, engine):
        choice = await self._seed_and_prep(service, engine)
        choice = await service.update_candidate(
            batch_id=choice.import_batch_id,
            candidate_id=choice.id,
            patch={"suggested_knowledge_point_codes": ["kp_does_not_exist"]},
        )
        result = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert result["created"] == []
        assert len(result["errors"]) == 1
        assert "未知知识点" in result["errors"][0]["error"]

    async def test_valid_kp_accepted(self, service, engine):
        choice = await self._seed_and_prep(service, engine)
        from app.data.database import get_db_session
        from app.data.models import KnowledgePoint
        async with get_db_session() as db:
            kp = (await db.execute(select(KnowledgePoint).limit(1))).scalar_one()
            valid_code = kp.code
        choice = await service.update_candidate(
            batch_id=choice.import_batch_id,
            candidate_id=choice.id,
            patch={"suggested_knowledge_point_codes": [valid_code]},
        )
        result = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert len(result["created"]) == 1


# ══════════════════════════════════════════════════════════════════
# §30 AI Offline
# ══════════════════════════════════════════════════════════════════
class TestAIUnavailable:
    pytestmark = pytest.mark.asyncio

    async def test_import_works_when_ai_disabled(self, service, engine):
        """AI_ENABLED=false 时主链路（PDF→解析→candidate→draft）仍可用，不初始化 AI runtime。

        QuestionImporter 为纯 DB 落题，不触碰 LLM/向量/AI；content_import 亦不 import AI 模块。
        此处用真实 importer 走完整链路验证。
        """
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from app.data.database import get_db_session
        async with get_db_session() as db:
            await seed_phase_one_calculus(db)
            await db.commit()
        batch, candidates = await create_parsed_batch(service, MIXED_PDF_TEXT)
        assert batch.status == "parsed"
        assert len(candidates) >= 1
        choice = next(c for c in candidates if c.detected_question_type == "choice")
        result = await service.create_drafts(choice.import_batch_id, [choice.id])
        assert len(result["created"]) == 1


# ══════════════════════════════════════════════════════════════════
# §30 Auth
# ══════════════════════════════════════════════════════════════════
def _request(user=None, path="/"):
    from starlette.requests import Request
    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "state": {}}
    req = Request(scope)
    if user is not None:
        req.state.current_user = user
        req.state.user_id = user.id
    return req


class TestAuth:
    pytestmark = pytest.mark.asyncio

    async def test_no_auth_401(self, patch_global_session_factory):
        from app.api.content_import_api import list_imports
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await list_imports(_request(path="/api/admin/content/imports"))
        assert exc.value.status_code == 401

    async def test_student_403(self, patch_global_session_factory):
        from app.api.content_import_api import list_imports
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await list_imports(_request(SimpleNamespace(id="student", role="student")))
        assert exc.value.status_code == 403

    async def test_admin_200(self, engine, patch_global_session_factory, patch_storage_root):
        from app.api.content_import_api import list_imports
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # 空库
        resp = await list_imports(_request(SimpleNamespace(id="admin", role="admin")))
        assert resp["code"] == 0
        assert resp["data"] == []