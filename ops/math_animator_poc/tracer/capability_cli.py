"""CLI for the local MathAnimationCapability admission gate."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .capability import AnimationCapabilityError, LocalMathAnimationCapability
from .local_queue import LocalFileTaskQueue, LocalQueueError
from .pipeline_cli import VisualSpecFileError, _load_visual_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate and submit a local animation request")
    parser.add_argument("visual_spec", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--template-id",
        required=True,
        choices=("secant_to_tangent", "riemann_sum", "taylor_approximation"),
    )
    parser.add_argument(
        "--trigger",
        required=True,
        choices=("user_explicit", "teaching_strategy", "none"),
    )
    parser.add_argument("--dynamic-process-score", type=float)
    parser.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()

    try:
        result = LocalMathAnimationCapability(
            LocalFileTaskQueue(args.root / "queue")
        ).submit(
            _load_visual_spec(args.visual_spec),
            args.template_id,
            trigger=args.trigger,
            dynamic_process_score=args.dynamic_process_score,
            idempotency_key=args.idempotency_key,
        )
    except (
        AnimationCapabilityError,
        LocalQueueError,
        OSError,
        VisualSpecFileError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=False))
        return 2

    print(
        json.dumps(
            {
                "decision": asdict(result.decision),
                "fallback": result.fallback,
                "job_id": result.job.job_id if result.job else None,
                "job_status": result.job.status if result.job else None,
                "status": result.status,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
