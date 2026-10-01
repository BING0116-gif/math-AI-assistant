"""Evaluate a RAG retrieval run against the versioned Phase 4 gold set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Keep ``python scripts/rag_quality_eval.py`` compatible with the canonical
# ``python -m scripts.rag_quality_eval`` entrypoint without package shadowing.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag_quality_eval.evaluator import evaluate_retrieval, load_json


def _markdown(report: dict) -> str:
    metrics = report["metrics"]
    lines = [
        "# RAG quality report",
        "",
        f"- Status: `{report['status']}`",
        f"- Mode: `{report['run']['mode']}`",
        f"- Gold: `{report['gold_version']}`",
        f"- Cases: {report['case_count']}",
        f"- Recall@{report['top_k']}: {metrics['recall_at_k']:.4f}",
        f"- MRR: {metrics['mrr']:.4f}",
        f"- Irrelevant recall rate: {metrics['irrelevant_recall_rate']:.4f}",
        f"- Latency p95: {metrics['latency_p95_ms']:.2f} ms",
        "",
        "## Case evidence",
        "",
        "| Case | Kind | Recall | RR | Forbidden | Degraded | Latency ms |",
        "| --- | --- | ---: | ---: | --- | --- | ---: |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['case_id']} | {case['kind']} | {case['recall_at_k']:.4f} | "
            f"{case['reciprocal_rank']:.4f} | {', '.join(case['forbidden_hits']) or '-'} | "
            f"{str(case['degraded']).lower()} | {case['latency_ms']:.2f} |"
        )
    if report["policy_failures"]:
        lines.extend(["", "## Policy failures", ""])
        lines.extend(f"- `{failure}`" for failure in report["policy_failures"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = evaluate_retrieval(load_json(args.gold), load_json(args.results))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
