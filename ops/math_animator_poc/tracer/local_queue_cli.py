"""CLI for submitting and processing local durable animation jobs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .local_queue import LocalFileTaskQueue, LocalQueueError, LocalQueueWorker
from .pipeline import LocalAnimationPipeline
from .pipeline_cli import VisualSpecFileError, _load_visual_spec


def _queue(root: Path) -> LocalFileTaskQueue:
    return LocalFileTaskQueue(root / "queue")


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local T15 animation jobs")
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    submit = commands.add_parser("submit")
    submit.add_argument("visual_spec", type=Path)
    submit.add_argument(
        "--template-id",
        required=True,
        choices=("secant_to_tangent", "riemann_sum", "taylor_approximation"),
    )
    submit.add_argument("--idempotency-key", required=True)

    work = commands.add_parser("work-once")
    work.add_argument("--worker-id", required=True)
    work.add_argument("--lease-seconds", type=float, default=60.0)

    status = commands.add_parser("status")
    status.add_argument("job_id")

    cancel = commands.add_parser("cancel")
    cancel.add_argument("job_id")

    args = parser.parse_args()
    queue = _queue(args.root)
    try:
        if args.command == "submit":
            job = queue.submit(
                _load_visual_spec(args.visual_spec),
                args.template_id,
                idempotency_key=args.idempotency_key,
            )
            _print(asdict(job))
            return 0
        if args.command == "work-once":
            worker = LocalQueueWorker(
                queue,
                LocalAnimationPipeline(args.root / "pipeline"),
                worker_id=args.worker_id,
                lease_seconds=args.lease_seconds,
            )
            job = worker.run_once()
            _print({"status": "idle"} if job is None else asdict(job))
            return 0
        if args.command == "status":
            job = queue.get(args.job_id)
            if job is None:
                _print({"status": "not_found"})
                return 1
            _print(asdict(job))
            return 0
        if args.command == "cancel":
            cancelled = queue.cancel(args.job_id)
            _print({"cancelled": cancelled, "job_id": args.job_id})
            return 0 if cancelled else 1
    except (OSError, LocalQueueError, VisualSpecFileError, ValueError) as exc:
        _print({"status": "rejected", "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
