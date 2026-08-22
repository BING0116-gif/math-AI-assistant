"""
Step 1.1-E2-A0 Content AI Analysis tests.

Covers:
- MockContentAIProvider deterministic + forced_case injection (= pass/doubtful/fail)
- QwenContentAIProvider stub unavailable (AI_PROVIDER_NOT_IMPLEMENTED)
- ContentAIProviderFactory.provider_status()
- ContentAIAnalysisService: analyze → run created (pass/doubtful/failed gate)
- history preserved across re-analyze (attempt_no + parent_run_id)
- human disposition (approved/doubtful/reject)
- create_draft_from_approved → Question(ai_provider='mock', is_ai_generated=True, answer=ground truth)
- mock publish protection (review service blocks ai_provider='mock')
- Alembic migration upgrade head applies on fresh SQLite (table + column present)
"""

import asyncio
import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import (
    Base,
    ContentImportCandidate,
    ImportBatch,
    Question,
    SourceDocument,
)
from app.services.content_ai_analysis import (
    ContentAIAnalysisService,
    MOCK_AI_RESULT_NOT_PUBLISHABLE,
    get_provider_status,
)
from app.services.content_ai_provider import (
    AI_PROVIDER_NOT_IMPLEMENTED,
    AI_PROVIDER_PARSE_FAILED,
    AI_PROVIDER_REQUEST_FAILED,
    ContentAIProviderError,
    ContentAIProviderFactory,
    DeepSeekContentAIProvider,
    DEEPSEEK_PROVIDER_NAME,
    MockContentAIProvider,
    QwenContentAIProvider,
    reset_for_test,
)
from app.services.content_review import ContentReviewError, ContentReviewService
from app.services.knowledge_seed import seed_phase_one_calculus


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
    import app.data.database as db

    monkeypatch.setattr(db, "async_session_factory", session_factory)
    yield session_factory


@pytest.fixture
def patch_storage_root(tmp_path, monkeypatch):
    from app.config.settings import settings

    root = tmp_path / "runtime" / "content"
    monkeypatch.setattr(settings, "CONTENT_STORAGE_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def _reset_provider_singleton():
    reset_for_test()
    yield
    reset_for_test()


@pytest.fixture(autouse=True)
def _force_test_provider(monkeypatch):
    """测试隔离：强制 Content AI provider 为 mock，避免读取真实 .env 中的 deepseek key。"""
    from app.config.settings import settings

    monkeypatch.setattr(settings, "CONTENT_AI_PROVIDER", "mock")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    reset_for_test()


# ── helpers ──
def _snapshot(candidate_id: str, qtype: str = "choice", answer: str = "A") -> dict:
    options = [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}] if qtype == "choice" else []
    return {
        "candidate_id": candidate_id,
        "detected_question_type": qtype,
        "options": options,
        "original_answer": answer,
        "original_solution": "sol",
        "stem": "f'(1)=?",
        "suggested_knowledge_point_codes": [],
    }


async def _make_batch(db) -> str:
    """Create a SourceDocument + parsed ImportBatch and return the batch id."""
    src = SourceDocument(
        id=str(uuid.uuid4()),
        original_filename="t.pdf",
        storage_key="originals/t.pdf",
        sha256="x" * 64,
        mime_type="application/pdf",
        size_bytes=10,
        created_by="admin-1",
        status="active",
    )
    db.add(src)
    await db.flush()
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        source_document_id=src.id,
        status="parsed",
        parser_name="quick",
        created_by="admin-1",
        stats={},
    )
    db.add(batch)
    await db.flush()
    return batch.id


async def _make_candidate(
    db, *, qtype: str = "choice", supported: bool = True, answer: str = "A",
    batch_id: Optional[str] = None,
) -> str:
    options = [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}] if qtype == "choice" else []
    if batch_id is None:
        batch_id = await _make_batch(db)
    cand = ContentImportCandidate(
        id=str(uuid.uuid4()),
        import_batch_id=batch_id,
        candidate_index=0,
        detected_question_type=qtype,
        supported=supported,
        stem="f'(1)=?",
        options=options,
        original_answer=answer,
        original_solution="sol",
        suggested_knowledge_point_codes=[],
        status="parsed",
    )
    db.add(cand)
    await db.flush()
    return cand.id


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ══════════════════════════════════════════════════════════════════
# Provider 单元测试
# ══════════════════════════════════════════════════════════════════
class TestMockProvider:
    def test_forced_pass(self):
        p = MockContentAIProvider()
        ctx = {"mock_case": "pass"}
        analysis = p.analyze(_snapshot("c1"), ctx)
        v = p.verify(analysis, _snapshot("c1"), ctx)
        assert v.verdict == "pass"

    def test_forced_doubtful(self):
        p = MockContentAIProvider()
        ctx = {"mock_case": "doubtful"}
        analysis = p.analyze(_snapshot("c2"), ctx)
        v = p.verify(analysis, _snapshot("c2"), ctx)
        assert v.verdict == "doubtful"

    def test_forced_fail(self):
        p = MockContentAIProvider()
        ctx = {"mock_case": "fail"}
        analysis = p.analyze(_snapshot("c3"), ctx)
        v = p.verify(analysis, _snapshot("c3"), ctx)
        assert v.verdict == "fail"

    def test_deterministic_distribution(self):
        p = MockContentAIProvider()
        cases = {p._decide_case(f"id-{i}") for i in range(200)}
        # 哈希分布应覆盖至少两种结果（确定性，不依赖随机）
        assert len(cases) >= 2


class TestQwenProvider:
    def test_stub_unavailable(self):
        p = QwenContentAIProvider()
        assert p.is_available() is False

    def test_stub_raises_not_implemented(self):
        p = QwenContentAIProvider()
        with pytest.raises(ContentAIProviderError) as e:
            p.analyze(_snapshot("q1"), {})
        assert e.value.code == AI_PROVIDER_NOT_IMPLEMENTED
        with pytest.raises(ContentAIProviderError) as e2:
            p.verify(None, _snapshot("q1"), {})
        assert e2.value.code == AI_PROVIDER_NOT_IMPLEMENTED


class TestFactory:
    def test_mock_status(self):
        st = ContentAIProviderFactory("mock").provider_status()
        assert st.provider == "mock"
        assert st.available is True

    def test_qwen_status_unavailable_without_key(self):
        st = ContentAIProviderFactory("qwen").provider_status()
        assert st.provider == "qwen"
        assert st.available is False
        # 即使真 key 缺失，也应暴露 unavailable 原因
        assert st.reason in ("not_implemented", "missing_api_key")


# ══════════════════════════════════════════════════════════════════
# Analysis Service 集成测试（依赖 SQLite + 全局 session factory）
# ══════════════════════════════════════════════════════════════════
class TestAnalysisService:
    @pytest.mark.asyncio
    async def test_analyze_creates_pass_run(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await db.commit()
        svc = ContentAIAnalysisService()
        run = await svc.analyze_candidate(cid, forced_case="pass")
        assert run.status == "pass"
        assert run.gate == "PASS"
        assert run.provider == "mock"

    @pytest.mark.asyncio
    async def test_analyze_fail_run(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await db.commit()
        run = await ContentAIAnalysisService().analyze_candidate(cid, forced_case="fail")
        assert run.status == "failed"
        assert run.gate == "FAILED"
        assert run.error_code is None  # fail 是正常 gate，不是 provider 错误

    @pytest.mark.asyncio
    async def test_history_and_reanalyze(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await db.commit()
        svc = ContentAIAnalysisService()
        first = await svc.analyze_candidate(cid, forced_case="pass")
        second = await svc.reanalyze_candidate(cid, forced_case="doubtful")
        assert second.attempt_no == 2
        assert second.parent_run_id == first.id
        history = (await svc.get_history(cid))
        assert len(history) == 2
        latest = (await svc.get_latest_run(cid))
        assert latest.id == second.id

    @pytest.mark.asyncio
    async def test_disposition(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await db.commit()
        svc = ContentAIAnalysisService()
        await svc.analyze_candidate(cid, forced_case="pass")
        run = await svc.set_human_disposition(cid, "approved")
        assert run.human_disposition == "approved"
        # 非法处置应报错
        with pytest.raises(Exception):
            await svc.set_human_disposition(cid, "bogus")

    @pytest.mark.asyncio
    async def test_create_draft_from_approved(
        self, engine, session_factory, patch_global_session_factory, monkeypatch
    ):
        await _create_tables(engine)
        # 指向一个独立临时目录（避免依赖 pytest tmp_path / .pytest_tmp 清理，
        # 该清理在当前 Windows 沙箱中因回收站不可用而失败）。
        import tempfile

        from app.config.settings import settings

        root = tempfile.mkdtemp(prefix="zhiwei_content_")
        monkeypatch.setattr(settings, "CONTENT_STORAGE_ROOT", root)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await seed_phase_one_calculus(db)
            await db.commit()
        svc = ContentAIAnalysisService()
        await svc.analyze_candidate(cid, forced_case="pass")
        await svc.set_human_disposition(cid, "approved")
        result = await svc.create_draft_from_approved(cid)
        assert result["created"], result
        qid = result["created"][0]
        async with session_factory() as db:
            q = await db.get(Question, qid)
            assert q is not None
            assert q.ai_provider == "mock"
            assert q.is_ai_generated is True
            # 原答案（ground truth）不被 AI 覆盖
            assert q.answer == "A"


# ══════════════════════════════════════════════════════════════════
# Mock 发布保护（服务端硬规则 §18）
# ══════════════════════════════════════════════════════════════════
class TestMockPublishProtection:
    @pytest.mark.asyncio
    async def test_mock_blocked(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            q = Question(
                id="Q-MOCK-1", content="x", question_type="judge", category="极限",
                answer="true", analysis="a", review_status="reviewed",
                ai_provider="mock",
            )
            db.add(q)
            await db.commit()
        svc = ContentReviewService()
        with pytest.raises(ContentReviewError) as e:
            await svc.publish("Q-MOCK-1")
        assert e.value.code == MOCK_AI_RESULT_NOT_PUBLISHABLE

    @pytest.mark.asyncio
    async def test_non_mock_not_blocked_by_mock_guard(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            q = Question(
                id="Q-QWEN-1", content="x", question_type="judge", category="极限",
                answer="true", analysis="a", review_status="reviewed",
                ai_provider="qwen",
            )
            db.add(q)
            await db.commit()
        svc = ContentReviewService()
        # qwen 题通过 mock 守卫（不会报 MOCK_AI_RESULT_NOT_PUBLISHABLE），
        # 但因内容不完整会在后续服务端校验失败 —— 验证守卫针对性。
        with pytest.raises(ContentReviewError) as e:
            await svc.publish("Q-QWEN-1")
        assert e.value.code != MOCK_AI_RESULT_NOT_PUBLISHABLE


# ══════════════════════════════════════════════════════════════════
# Alembic 迁移冒烟（fresh SQLite：empty → head）
# ══════════════════════════════════════════════════════════════════
class TestAlembicMigration:
    def test_head_is_new_migration(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "app", "data", "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
        assert script.get_current_head() == "a3b4c5d6e7f8"

    def test_upgrade_head_on_sqlite(self):
        import sqlite3
        import tempfile

        from alembic import command
        from alembic.config import Config

        tmp = tempfile.gettempdir()
        db_path = os.path.join(tmp, "zhiwei_mig_smoke.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        url = "sqlite:///" + db_path.replace("\\", "/")

        old = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            cfg = Config(os.path.join(os.path.dirname(__file__), "..", "app", "data", "alembic.ini"))
            command.upgrade(cfg, "head")
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='content_ai_analysis_runs'"
        )
        assert cur.fetchone() is not None
        cur.execute("PRAGMA table_info(questions)")
        assert any(r[1] == "ai_provider" for r in cur.fetchall())
        cur.execute("PRAGMA table_info(content_ai_analysis_runs)")
        cols = [r[1] for r in cur.fetchall()]
        assert "parent_run_id" in cols
        conn.close()
        os.remove(db_path)


# ── DeepSeek 真实 provider（不联网，仅验证装配 / 可用性 / 解析健壮性）──
class TestDeepSeekProvider:
    def test_unavailable_without_key(self):
        p = DeepSeekContentAIProvider(api_key="")
        assert p.is_available() is False
        # 无 key 时 analyze / verify 应抛 NOT_IMPLEMENTED（而非发起网络请求）
        with pytest.raises(ContentAIProviderError) as exc:
            p.analyze({"candidate_id": "x"}, {})
        assert exc.value.code == AI_PROVIDER_NOT_IMPLEMENTED
        with pytest.raises(ContentAIProviderError) as exc2:
            p.verify(None, {"candidate_id": "x"}, {})
        assert exc.value.code == AI_PROVIDER_NOT_IMPLEMENTED

    def test_available_with_key(self):
        p = DeepSeekContentAIProvider(api_key="sk-test", model="deepseek-chat")
        assert p.is_available() is True
        assert p.model == "deepseek-chat"
        assert p.name == DEEPSEEK_PROVIDER_NAME

    def test_parse_json_strips_fences_and_recovers(self):
        p = DeepSeekContentAIProvider(api_key="sk-test")
        # 标准 JSON
        assert p._parse_json('{"verdict":"pass"}') == {"verdict": "pass"}
        # 带 ```json 围栏
        assert p._parse_json('```json\n{"verdict":"doubtful"}\n```') == {"verdict": "doubtful"}
        # 夹杂多余文本，抽取首个对象
        assert p._parse_json('无关说明 {"verdict":"fail"} 结束') == {"verdict": "fail"}

    def test_parse_json_invalid_raises(self):
        p = DeepSeekContentAIProvider(api_key="sk-test")
        with pytest.raises(ContentAIProviderError) as exc:
            p._parse_json("这根本不是 json")
        assert exc.value.code == AI_PROVIDER_PARSE_FAILED

    def test_factory_resolves_deepseek(self, monkeypatch):
        from app.config.settings import settings

        # pydantic settings 为缓存单例，setenv 不生效，需直接改属性
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-test")
        factory = ContentAIProviderFactory(provider="deepseek")
        provider = factory.get_provider()
        assert isinstance(provider, DeepSeekContentAIProvider)
        status = factory.provider_status()
        assert status.provider == DEEPSEEK_PROVIDER_NAME
        assert status.available is True

    def test_factory_deepseek_missing_key_unavailable(self, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        factory = ContentAIProviderFactory(provider="deepseek")
        status = factory.provider_status()
        assert status.available is False
        assert status.reason == "missing_api_key"


# ── 批量操作与简化流程（新增）──
class TestBatchOperations:
    @pytest.mark.asyncio
    async def test_analyze_batch_analyzes_unsupported_too(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            batch_id = await _make_batch(db)
            cid1 = await _make_candidate(db, qtype="choice", supported=True, answer="A", batch_id=batch_id)
            cid2 = await _make_candidate(db, qtype="calculation", supported=False, answer="x=1", batch_id=batch_id)
            await db.commit()
        svc = ContentAIAnalysisService()
        result = await svc.analyze_batch(batch_id, concurrency=2)
        # unsupported 题型现在也被分析
        assert result["analyzed"] == 2
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_batch_set_disposition(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid1 = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            cid2 = await _make_candidate(db, qtype="choice", supported=True, answer="B")
            await db.commit()
        svc = ContentAIAnalysisService()
        await svc.analyze_candidate(cid1, forced_case="pass")
        await svc.analyze_candidate(cid2, forced_case="pass")
        result = await svc.batch_set_disposition([cid1, cid2], "approved")
        assert len(result["ok"]) == 2
        latest1 = await svc.get_latest_run(cid1)
        assert latest1.human_disposition == "approved"

    @pytest.mark.asyncio
    async def test_batch_create_drafts_and_publish(
        self, engine, session_factory, patch_global_session_factory, monkeypatch
    ):
        await _create_tables(engine)
        import tempfile
        from app.config.settings import settings

        root = tempfile.mkdtemp(prefix="zhiwei_content_")
        monkeypatch.setattr(settings, "CONTENT_STORAGE_ROOT", root)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            await seed_phase_one_calculus(db)
            await db.commit()
        svc = ContentAIAnalysisService()
        await svc.analyze_candidate(cid, forced_case="pass")
        await svc.set_human_disposition(cid, "approved")
        draft_res = await svc.batch_create_drafts([cid])
        assert draft_res["created"], draft_res
        qid = draft_res["created"][0]

        # 修改 ai_provider 为 deepseek（模拟真实 AI）以便通过 publish 的 mock 守卫
        async with session_factory() as db:
            q = await db.get(Question, qid)
            q.ai_provider = "deepseek"
            await db.commit()

        review_svc = ContentReviewService()
        pub_res = await review_svc.batch_publish([qid])
        assert qid in pub_res["published"], pub_res

    @pytest.mark.asyncio
    async def test_async_analyze_batch_task(
        self, engine, session_factory, patch_global_session_factory
    ):
        await _create_tables(engine)
        async with session_factory() as db:
            cid = await _make_candidate(db, qtype="choice", supported=True, answer="A")
            batch_id = (await db.execute(
                select(ContentImportCandidate.import_batch_id).where(ContentImportCandidate.id == cid)
            )).scalar()
            await db.commit()
        svc = ContentAIAnalysisService()
        task_id = await svc.start_analyze_batch_task(batch_id, concurrency=2)
        assert task_id.startswith("bat-")
        # P0-2：持久化任务由 Worker 执行 —— 测试进程内直接驱动处理
        from app.workers.content_worker import process_task

        final = await process_task(task_id)
        task = await svc.get_batch_task(task_id)
        assert task is not None
        assert task["status"] == "completed"
        assert task["result"]["analyzed"] == 1


class TestDeepSeekAnalyzeAndVerify:
    def test_single_prompt_returns_both(self):
        p = DeepSeekContentAIProvider(api_key="sk-test")
        snapshot = {
            "candidate_id": "c1",
            "detected_question_type": "choice",
            "stem": "1+1=?",
            "options": [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}],
            "original_answer": "A",
            "original_solution": "2",
            "suggested_knowledge_point_codes": [],
        }
        prompt = p._build_single_prompt(snapshot, {"known_knowledge_point_codes": []})
        assert "verification" in prompt
        assert "question_type" in prompt

    def test_analyze_and_verify_not_called_without_key(self):
        p = DeepSeekContentAIProvider(api_key="")
        with pytest.raises(ContentAIProviderError) as exc:
            p.analyze_and_verify({"candidate_id": "x"}, {})
        assert exc.value.code == AI_PROVIDER_NOT_IMPLEMENTED
