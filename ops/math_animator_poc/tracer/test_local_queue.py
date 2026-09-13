from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from app.services.math_visualizer import mock_visual_spec

from ops.math_animator_poc.tracer.local_queue import (
    IdempotencyConflict,
    LocalFileTaskQueue,
    LocalQueueError,
    LocalQueueWorker,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)
from ops.math_animator_poc.tracer.models import MathAnimationSpec
from ops.math_animator_poc.tracer.pipeline import PipelineResult
from ops.math_animator_poc.tracer.runner import RenderResult


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 13, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class FakePipeline:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls = 0

    def run_from_visual_spec(self, raw_visual_spec, requested_template_id):
        self.calls += 1
        event_log = self.root / f"event-{self.calls}.jsonl"
        event_log.parent.mkdir(parents=True, exist_ok=True)
        event_log.write_text('{"stage":"pipeline","status":"succeeded"}\n')
        render = RenderResult(
            "succeeded",
            "cache-key",
            self.root / "animation.mp4",
            1,
            False,
        )
        return PipelineResult(
            "succeeded",
            f"run-{self.calls}",
            event_log,
            MathAnimationSpec.from_mapping(
                {"schema_version": 1, "template_id": requested_template_id, "parameters": {}}
            ),
            render,
        )


class LocalFileTaskQueueTest(unittest.TestCase):
    def test_submit_is_idempotent_and_conflict_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            first = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="request-1",
            )
            duplicate = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="request-1",
            )
            with self.assertRaises(IdempotencyConflict):
                queue.submit(
                    mock_visual_spec("function_plot"),
                    "secant_to_tangent",
                    idempotency_key="request-1",
                )

        self.assertEqual(first.job_id, duplicate.job_id)
        self.assertEqual(first.request_sha256, duplicate.request_sha256)

    def test_claim_heartbeat_and_worker_ownership(self) -> None:
        clock = MutableClock()
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory), clock=clock)
            submitted = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="request-2",
            )
            claimed = queue.claim_next("worker-a", lease_seconds=30)
            self.assertEqual(claimed.job_id, submitted.job_id)
            self.assertEqual(claimed.status, STATUS_RUNNING)
            self.assertIsNone(queue.claim_next("worker-b", lease_seconds=30))
            self.assertFalse(queue.heartbeat(claimed.job_id, "worker-b", lease_seconds=30))
            clock.value += timedelta(seconds=10)
            self.assertTrue(queue.heartbeat(claimed.job_id, "worker-a", lease_seconds=30))

    def test_stale_short_lock_is_recovered_after_process_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory), stale_lock_seconds=5)
            job = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="stale-lock",
            )
            lock_dir = queue.jobs_root / job.job_id / ".lock"
            lock_dir.mkdir()
            old = time.time() - 10
            os.utime(lock_dir, (old, old))
            recovered = queue.get(job.job_id)

        self.assertEqual(recovered.job_id, job.job_id)

    def test_expired_lease_is_recovered_by_another_worker(self) -> None:
        clock = MutableClock()
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory), clock=clock)
            queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="request-3",
            )
            first = queue.claim_next("worker-a", lease_seconds=5)
            clock.value += timedelta(seconds=6)
            recovered = queue.claim_next("worker-b", lease_seconds=5)

        self.assertEqual(recovered.job_id, first.job_id)
        self.assertEqual(recovered.worker_id, "worker-b")
        self.assertEqual(recovered.claim_count, 2)
        self.assertEqual(recovered.recovery_count, 1)

    def test_pending_and_running_cancel_are_cooperative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            pending = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="cancel-pending",
            )
            self.assertTrue(queue.cancel(pending.job_id))
            self.assertEqual(queue.get(pending.job_id).status, STATUS_CANCELLED)

            running = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="cancel-running",
            )
            queue.claim_next("worker-a")
            self.assertTrue(queue.cancel(running.job_id))
            final = queue.finish(running.job_id, "worker-a", status=STATUS_SUCCEEDED)
            self.assertEqual(final.status, STATUS_CANCELLED)

    def test_worker_completes_and_persists_pipeline_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = LocalFileTaskQueue(root / "queue")
            pipeline = FakePipeline(root / "pipeline")
            submitted = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="worker-success",
            )
            final = LocalQueueWorker(
                queue,
                pipeline,
                worker_id="worker-a",
                lease_seconds=5,
            ).run_once()

        self.assertEqual(final.job_id, submitted.job_id)
        self.assertEqual(final.status, STATUS_SUCCEEDED)
        self.assertEqual(final.pipeline_run_id, "run-1")
        self.assertTrue(final.pipeline_event_log.endswith("event-1.jsonl"))

    def test_tampered_request_fails_without_running_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = LocalFileTaskQueue(root / "queue")
            pipeline = FakePipeline(root / "pipeline")
            job = queue.submit(
                mock_visual_spec("tangent_line"),
                "secant_to_tangent",
                idempotency_key="tamper-check",
            )
            request_path = queue.jobs_root / job.job_id / "request.json"
            request_path.write_text(json.dumps({"template_id": "evil", "visual_spec": {}}))
            final = LocalQueueWorker(queue, pipeline, worker_id="worker-a").run_once()

        self.assertEqual(final.status, STATUS_FAILED)
        self.assertIn("hash mismatch", final.error)
        self.assertEqual(pipeline.calls, 0)

    def test_ids_and_non_finite_requests_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = LocalFileTaskQueue(Path(directory))
            with self.assertRaises(LocalQueueError):
                queue.submit({}, "secant_to_tangent", idempotency_key="../escape")
            with self.assertRaises(LocalQueueError):
                queue.submit(
                    {"value": float("nan")},
                    "secant_to_tangent",
                    idempotency_key="finite-only",
                )


if __name__ == "__main__":
    unittest.main()
