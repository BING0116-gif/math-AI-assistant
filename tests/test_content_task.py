"""P0-1/2 持久化任务系统测试（content_tasks + worker）。"""

import pytest
import fitz
from datetime import datetime, timedelta, timezone
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, ContentTask
from app.services.content_import import ContentImportService, MODE_QUICK
from app.services.content_task import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RETRYING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    cancel_task,
    claim_next_task,
    complete_task,
    enqueue_task,
    fail_task,
    get_task,
)
from app.workers.content_worker import process_task


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


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontname="china-s", encoding="gbk")
    data = doc.tobytes()
    doc.close()
    return data


class TestTaskLifecycle:
    pytestmark = pytest.mark.asyncio

    async def test_enqueue_claim_complete(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        task = await enqueue_task("import_parse", "batch-1", max_retries=3)
        assert task.status == STATUS_PENDING

        claimed = await claim_next_task("worker-a")
        assert claimed is not None and claimed.id == task.id
        assert claimed.status == STATUS_RUNNING
        assert claimed.worker_id == "worker-a"

        # 同一任务不能被第二个 Worker 认领
        assert await claim_next_task("worker-b") is None

        await complete_task(task.id, STATUS_SUCCEEDED, progress={"total": 1, "done": 1})
        fresh = await get_task(task.id)
        assert fresh.status == STATUS_SUCCEEDED
        assert fresh.progress == {"total": 1, "done": 1}
        assert fresh.completed_at is not None

    async def test_retry_then_failed(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        task = await enqueue_task("import_parse", "batch-1", max_retries=1)

        claimed = await claim_next_task("worker-a")
        await fail_task(claimed.id, "PARSE_TIMEOUT", "超时")
        t1 = await get_task(task.id)
        assert t1.status == STATUS_RETRYING
        assert t1.retry_count == 1
        assert t1.next_run_at is not None

        # 退避期内不可认领；把 next_run_at 拨回过去后可再次认领
        async with session_factory() as db:
            await db.execute(
                update(ContentTask)
                .where(ContentTask.id == task.id)
                .values(next_run_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            await db.commit()
        claimed2 = await claim_next_task("worker-a")
        assert claimed2 is not None
        await fail_task(claimed2.id, "PARSE_TIMEOUT", "再次超时")
        t2 = await get_task(task.id)
        assert t2.status == STATUS_FAILED
        assert t2.error_code == "PARSE_TIMEOUT"

    async def test_cancel_pending(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        task = await enqueue_task("ai_batch_analyze", "batch-1")
        ok = await cancel_task(task.id)
        assert ok is True
        assert (await get_task(task.id)).status == STATUS_CANCELLED

    async def test_multi_worker_claim_distinct(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        t1 = await enqueue_task("import_parse", "b1")
        t2 = await enqueue_task("import_parse", "b2")
        got_a = await claim_next_task("worker-a")
        got_b = await claim_next_task("worker-b")
        assert {got_a.id, got_b.id} == {t1.id, t2.id}
        assert got_a.worker_id == "worker-a"
        assert got_b.worker_id == "worker-b"


class TestWorkerProcessing:
    pytestmark = pytest.mark.asyncio

    async def test_import_parse_task_processes_batch(
        self, engine, session_factory, patch_global_session_factory, patch_storage_root
    ):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from app.services.content_import import ContentImportService

        service = ContentImportService()
        batch, created = await service.create_import(
            admin_user_id="admin-1",
            original_filename="test.pdf",
            content=make_pdf("一、选择题\n1. 求 f(x)=x^2 的导数。\nA. 2x\nB. x\n答案：A\n"),
            mode=MODE_QUICK,
        )
        assert created is True
        assert batch.status != "parsed"

        task = await enqueue_task("import_parse", batch.id, max_retries=3)
        final = await process_task(task.id)
        assert final == STATUS_SUCCEEDED

        fresh_batch = await service.get_batch(batch.id)
        assert fresh_batch.status == "parsed"
        candidates = await service.list_candidates(batch.id)
        assert len(candidates) >= 1

    async def test_worker_cancels_before_run(self, engine, session_factory, patch_global_session_factory):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        task = await enqueue_task("ai_batch_analyze", "batch-x")
        # 先取消 pending 任务，process_task 不应执行
        ok = await cancel_task(task.id)
        assert ok is True
        final = await process_task(task.id)
        assert final == "cancelled"
