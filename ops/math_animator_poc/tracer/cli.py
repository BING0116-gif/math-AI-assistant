"""Command-line entrypoint for the local-only T15 tracer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import MathAnimationSpec, SpecValidationError
from .runner import LocalTracerRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a reviewed T15 animation template")
    parser.add_argument("spec", type=Path, help="path to a MathAnimationSpec JSON file")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    try:
        spec = MathAnimationSpec.from_json_bytes(args.spec.read_bytes())
        result = LocalTracerRunner(
            args.output_root,
            timeout_seconds=args.timeout_seconds,
        ).render(spec)
    except (OSError, SpecValidationError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=False))
        return 2

    print(
        json.dumps(
            {
                "attempts": result.attempts,
                "cache_hit": result.cache_hit,
                "cache_key": result.cache_key,
                "error": result.error,
                "fallback": result.fallback,
                "output_path": str(result.output_path) if result.output_path else None,
                "status": result.status,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
