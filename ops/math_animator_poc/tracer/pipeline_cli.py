"""CLI for the local T08-to-animation observable pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .pipeline import LocalAnimationPipeline


MAX_VISUAL_SPEC_BYTES = 512 * 1024


class VisualSpecFileError(ValueError):
    pass


def _no_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VisualSpecFileError(f"duplicate JSON field: {key!r}")
        value[key] = item
    return value


def _load_visual_spec(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_VISUAL_SPEC_BYTES:
        raise VisualSpecFileError(f"visual spec exceeds {MAX_VISUAL_SPEC_BYTES} bytes")
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_fields)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisualSpecFileError("visual spec is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise VisualSpecFileError("visual spec must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt a T08 visual and run the local animation pipeline")
    parser.add_argument("visual_spec", type=Path)
    parser.add_argument(
        "--template-id",
        required=True,
        choices=("secant_to_tangent", "riemann_sum", "taylor_approximation"),
    )
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        visual_spec = _load_visual_spec(args.visual_spec)
        result = LocalAnimationPipeline(args.output_root).run_from_visual_spec(
            visual_spec,
            args.template_id,
        )
    except (OSError, VisualSpecFileError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=False))
        return 2

    render = result.render_result
    print(
        json.dumps(
            {
                "attempts": render.attempts if render else 0,
                "cache_hit": render.cache_hit if render else False,
                "cache_key": render.cache_key if render else None,
                "error": result.error,
                "event_log": str(result.event_log),
                "fallback": result.fallback,
                "output_path": str(render.output_path) if render and render.output_path else None,
                "run_id": result.run_id,
                "status": result.status,
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
