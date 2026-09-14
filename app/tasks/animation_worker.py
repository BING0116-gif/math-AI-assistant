"""Dedicated production animation worker entrypoint; never imported by FastAPI."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from app.config.settings import settings
from app.data.database import close_db, get_db_session, init_db
from app.services.animation_renderer import OneShotAnimationRunner
from app.services.animation_worker_state import (
    begin_animation_attempt,
    claim_next_animation_job,
    fail_animation_attempt,
    finish_animation_job,
    heartbeat_animation_job,
)

logger = logging.getLogger(__name__)


class AnimationWorker:
    def __init__(self, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.runner = OneShotAnimationRunner()

    async def run_once(self) -> bool:
        async with get_db_session() as db:
            job = await claim_next_animation_job(db, worker_id=self.worker_id)
            if job is None:
                return False
            job_id, template_id = job.id, job.template_id
            image_digest, source_sha256 = job.renderer_image_digest, job.template_source_sha256
        async with get_db_session() as db:
            started = await begin_animation_attempt(
                db, job_id=job_id, worker_id=self.worker_id,
                event_id=f"attempt-{uuid.uuid4().hex[:24]}",
            )
            if started is None:
                return True

        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id, stop_heartbeat))
        try:
            result = await asyncio.to_thread(
                self.runner.render_once,
                job_id=job_id,
                template_id=template_id,
                expected_image_digest=image_digest,
                expected_source_sha256=source_sha256,
            )
        finally:
            stop_heartbeat.set()
            await heartbeat_task
        async with get_db_session() as db:
            if result.succeeded:
                await finish_animation_job(
                    db, job_id=job_id, worker_id=self.worker_id,
                    event_id=f"success-{uuid.uuid4().hex[:24]}", artifact=result.artifact,
                )
            else:
                await fail_animation_attempt(
                    db, job_id=job_id, worker_id=self.worker_id,
                    event_id=f"failure-{uuid.uuid4().hex[:24]}",
                    error_code=result.error_code or "RENDER_FAILED",
                )
        return True

    async def _heartbeat_loop(self, job_id: str, stop: asyncio.Event) -> None:
        interval = max(3, settings.ANIMATION_JOB_LEASE_SECONDS // 3)
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                async with get_db_session() as db:
                    beat = await heartbeat_animation_job(
                        db, job_id=job_id, worker_id=self.worker_id
                    )
                if not beat.accepted or beat.cancel_requested:
                    return

    async def run_forever(self) -> None:
        if not settings.MATH_ANIMATION_ENABLED:
            logger.info("MathAnimator disabled; worker exits without querying SQL")
            return
        while True:
            worked = await self.run_once()
            if not worked:
                await asyncio.sleep(1)


async def _main() -> None:
    database_url = settings.ASYNC_DATABASE_URL or settings.DATABASE_URL
    if not database_url.startswith("postgresql"):
        raise RuntimeError("animation worker requires an explicit PostgreSQL database URL")
    await init_db()
    try:
        await AnimationWorker().run_forever()
    finally:
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
