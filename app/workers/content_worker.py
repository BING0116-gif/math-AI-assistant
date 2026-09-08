"""Content worker — P0-1/2 独立异步任务执行进程。

运行：python -m app.workers.content_worker

职责：
- 轮询认领 content_tasks 中 pending/retrying 任务（条件 UPDATE，多实例安全）
- import_parse      ：调用 ContentImportService.parse_import（MinerU 子进程解析移出 API 请求线程）
- ai_batch_analyze  ：调用 ContentAIAnalysisService 批量分析，进度写回任务表
- 心跳 / 指数退避重试 / 取消中断（候选间检查 cancel_requested）

测试可复用 process_task() 在进程内同步驱动单个任务。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.data.database import get_db_session
from app.data.models import ContentTask
from app.services.content_task import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_PENDING,
    STATUS_RETRYING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TaskCancelled,
    claim_next_task,
    complete_task,
    fail_task,
    get_task,
    is_cancel_requested,
    update_progress,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_task_by_id(task_id: str, worker_id: str) -> Optional[ContentTask]:
    """按 id 认领（测试/单次处理用）：仅 pending/retrying 可认领。"""
    async with get_db_session() as db:
        from sqlalchemy import update
        res = await db.execute(
            update(ContentTask)
            .where(ContentTask.id == task_id, ContentTask.status.in_((STATUS_PENDING, STATUS_RETRYING)))
            .values(
                status=STATUS_RUNNING,
                worker_id=worker_id,
                started_at=_now(),
                heartbeat_at=_now(),
                updated_at=_now(),
            )
        )
        if res.rowcount != 1:
            return None
        return await db.get(ContentTask, task_id)


# ── 任务处理器 ──
async def _handle_import_parse(task: ContentTask) -> str:
    from app.services.content_import import ContentImportService, ContentParseError

    svc = ContentImportService()
    try:
        batch = await svc.parse_import(task.ref_id)
    except ContentParseError as e:
        await fail_task(task.id, e.code, e.message)
        return await _current_status(task.id)
    await complete_task(
        task.id,
        STATUS_SUCCEEDED,
        progress={"total": 1, "done": 1, "batch_status": batch.status},
    )
    return STATUS_SUCCEEDED


async def _handle_ai_batch(task: ContentTask) -> str:
    from app.services.content_ai_analysis import ContentAIAnalysisService

    payload = task.payload or {}
    concurrency = int(payload.get("concurrency", 5))
    svc = ContentAIAnalysisService()
    candidates = await svc._load_batch_candidates(task.ref_id)
    total = len(candidates)
    await update_progress(task.id, total=total, done=0, skipped=0, errors=[], result=None)

    async def _progress_cb(*, total: int, analyzed: int) -> None:
        if await is_cancel_requested(task.id):
            raise TaskCancelled()
        await update_progress(task.id, total=total, done=analyzed)

    result = await svc._analyze_candidates(
        candidates,
        concurrency=concurrency,
        analyze_unsupported=True,
        progress_callback=_progress_cb,
    )
    status = STATUS_PARTIAL if result.get("errors") else STATUS_SUCCEEDED
    await complete_task(
        task.id,
        status,
        progress={
            "total": total,
            "done": result.get("analyzed", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", []),
            "result": {
                "analyzed": result.get("analyzed", 0),
                "skipped": result.get("skipped", 0),
                "errors": result.get("errors", []),
            },
        },
    )
    return status


_HANDLERS: Dict[str, Callable[[ContentTask], Any]] = {
    "import_parse": _handle_import_parse,
    "ai_batch_analyze": _handle_ai_batch,
}


async def _current_status(task_id: str) -> str:
    task = await get_task(task_id)
    return task.status if task else STATUS_FAILED


async def _run(task: ContentTask) -> str:
    """执行已认领任务（统一取消检查 + 异常兜底）。"""
    if await is_cancel_requested(task.id):
        await complete_task(task.id, STATUS_CANCELLED)
        return STATUS_CANCELLED
    handler = _HANDLERS.get(task.kind)
    if handler is None:
        await fail_task(task.id, "UNKNOWN_KIND", f"未知任务类型: {task.kind}")
        return await _current_status(task.id)
    try:
        return await handler(task)
    except TaskCancelled:
        await complete_task(task.id, STATUS_CANCELLED)
        return STATUS_CANCELLED
    except Exception as e:  # noqa: BLE001
        logger.exception("task %s 处理异常", task.id)
        await fail_task(task.id, "WORKER_ERROR", str(e)[:500])
        return await _current_status(task.id)


# ── 对外入口 ──
async def process_task(task_id: str, worker_id: str = "test-worker") -> str:
    """认领并处理单个任务（测试/运维复用）。返回最终状态。"""
    task = await claim_task_by_id(task_id, worker_id)
    if task is None:
        t = await get_task(task_id)
        return t.status if t else "not-found"
    return await _run(task)


async def worker_loop(
    worker_id: Optional[str] = None,
    poll_interval: float = 2.0,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    logger.info("content worker 启动: %s", worker_id)
    while stop_event is None or not stop_event.is_set():
        task = await claim_next_task(worker_id)
        if task is None:
            await asyncio.sleep(poll_interval)
            continue
        try:
            final = await _run(task)
            logger.info("task %s(%s) → %s", task.id, task.kind, final)
        except Exception as e:  # noqa: BLE001
            logger.exception("task %s 处理异常", task.id)
            await fail_task(task.id, "WORKER_LOOP_ERROR", str(e)[:500])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-6s | %(name)s | %(message)s",
    )
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
