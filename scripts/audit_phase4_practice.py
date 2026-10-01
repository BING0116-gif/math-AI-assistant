"""Generate Phase 4 machine-audit evidence and an accountable review sheet."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from content_quality_eval.phase4_practice import audit_phase4_practice


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviews")
    args = parser.parse_args()
    reviews = None
    if args.reviews:
        reviews = json.loads(Path(args.reviews).read_text(encoding="utf-8"))
    report = audit_phase4_practice(reviews)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output / "human-review-template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "question_id", "knowledge_code", "knowledge_name", "level", "difficulty",
            "required", "decision", "reviewer", "note",
        ])
        writer.writeheader()
        required = set(report["human_review"]["missing_ids"])
        for row in report["questions"]:
            writer.writerow({
                "question_id": row["question_id"],
                "knowledge_code": row["knowledge_code"],
                "knowledge_name": row["knowledge_name"],
                "level": row["level"],
                "difficulty": row["difficulty"],
                "required": "yes" if row["question_id"] in required else "no",
                "decision": "",
                "reviewer": "",
                "note": "",
            })
    summary = {
        "status": report["status"],
        "machine_passed": report["machine_checks"]["passed"],
        "question_count": report["question_count"],
        "human_review_required": report["human_review"]["required_count"],
        "human_review_approved": report["human_review"]["approved_count"],
        "bank_hash": report["bank_hash"],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["machine_checks"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
