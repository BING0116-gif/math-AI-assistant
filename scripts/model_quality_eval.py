"""CLI for validating, executing, comparing, and promoting Step 3.4 evaluations."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from model_quality_eval.dataset import DatasetValidationError, load_dataset
from model_quality_eval.reporting import (
    apply_human_reviews,
    build_human_review_template,
    compare_reports,
    comparison_markdown,
    load_report,
    report_markdown,
    write_json,
)
from model_quality_eval.runner import new_run_id, run_live_sync, run_mocked


def _selection(bundle, args):
    cases = list(bundle.cases)
    if getattr(args, "case_id", None):
        cases = [case for case in cases if case.case_id in set(args.case_id)]
    if getattr(args, "category", None):
        cases = [case for case in cases if case.primary_category.value in set(args.category)]
    if getattr(args, "modality", None):
        cases = [case for case in cases if case.modality in set(args.modality)]
    if getattr(args, "tutor_mode", None):
        cases = [case for case in cases if case.tutor_mode.value in set(args.tutor_mode)]
    if not cases:
        raise DatasetValidationError("case filters selected no cases")
    return cases


def _write_report(output: Path, report: dict) -> None:
    write_json(output / "results.json", report)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text(report_markdown(report), encoding="utf-8")


def command_validate(args) -> int:
    bundle = load_dataset(args.dataset)
    print(json.dumps({
        "status": "valid",
        "dataset_version": bundle.manifest.dataset_version,
        "dataset_hash": bundle.computed_hash,
        "case_count": len(bundle.cases),
    }, ensure_ascii=False))
    return 0


def command_run(args) -> int:
    bundle = load_dataset(args.dataset)
    selected = _selection(bundle, args)
    run_id = args.run_id or new_run_id(args.label)
    existing_path = Path(args.output) / "results.json"
    if existing_path.is_file():
        existing = load_report(existing_path)
        if (
            existing.get("run_id") == run_id
            and existing.get("dataset_hash") == bundle.computed_hash
            and existing.get("mode") == args.mode
            and existing.get("selected_case_ids") == [case.case_id for case in selected]
        ):
            print(json.dumps({
                "run_id": run_id,
                "status": existing["status"],
                "output": str(Path(args.output).resolve()),
                "resumed": True,
            }, ensure_ascii=False))
            return 2 if existing["status"] in {"not_run", "incomplete", "rejected"} else 0
    if args.mode == "mocked":
        report = run_mocked(bundle, run_id=run_id, label=args.label, selected=selected)
    else:
        report = run_live_sync(
            bundle,
            run_id=run_id,
            label=args.label,
            selected=selected,
            checkpoint_path=Path(args.output) / "checkpoint.json",
        )
    _write_report(Path(args.output), report)
    print(json.dumps({"run_id": run_id, "status": report["status"], "output": str(Path(args.output).resolve())}, ensure_ascii=False))
    if report["status"] in {"not_run", "incomplete", "rejected"}:
        return 2
    return 0


def command_compare(args) -> int:
    baseline, candidate = load_report(args.baseline), load_report(args.candidate)
    comparison = compare_reports(
        baseline,
        candidate,
        allow_cost_regression=args.allow_cost_regression,
        cost_exception_note=args.cost_exception_note,
    )
    output = Path(args.output)
    write_json(output / "comparison.json", comparison)
    (output / "comparison.md").write_text(comparison_markdown(comparison), encoding="utf-8")
    print(json.dumps({"status": comparison["status"], "output": str(output.resolve())}, ensure_ascii=False))
    return 0 if comparison["status"] == "approved" else 3


def command_review(args) -> int:
    report = load_report(args.report)
    review = yaml.safe_load(Path(args.review_file).read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError("review file must be a mapping")
    updated = apply_human_reviews(report, review)
    output = Path(args.output)
    _write_report(output, updated)
    print(json.dumps({"status": updated["status"], "output": str(output.resolve())}, ensure_ascii=False))
    return 0 if updated["status"] == "baseline_only" else 2


def command_review_template(args) -> int:
    report = load_report(args.report)
    template = build_human_review_template(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps({"status": "created", "output": str(output.resolve())}, ensure_ascii=False))
    return 0


def command_promote(args) -> int:
    report = load_report(args.report)
    if report.get("mode") != "live":
        raise ValueError("only live reports can be promoted")
    if report.get("status") not in {"baseline_only", "approved"}:
        raise ValueError("only complete, non-rejected live reports can be promoted")
    if not report.get("full_dataset", False):
        raise ValueError("filtered runs cannot be promoted")
    if len(args.reviewer.strip()) < 3 or args.reviewer.startswith("step3.4-"):
        raise ValueError("an accountable human reviewer identifier is required")
    if not report.get("human_review"):
        raise ValueError("a completed human quality review is required before promotion")
    if len(args.note.strip()) < 10:
        raise ValueError("promotion requires a substantive approval note")
    destination = Path(args.destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    promoted = dict(report)
    promoted["status"] = "approved"
    promoted["approval"] = {
        "reviewer": args.reviewer,
        "note": args.note,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(destination, promoted)
    destination.with_suffix(".md").write_text(report_markdown(promoted), encoding="utf-8")
    print(json.dumps({"status": "approved", "destination": str(destination.resolve())}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3 Step 3.4 model quality evaluation")
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("--dataset", required=True)
    validate.set_defaults(handler=command_validate)

    run = subcommands.add_parser("run")
    run.add_argument("--dataset", required=True)
    run.add_argument("--mode", choices=("mocked", "live"), required=True)
    run.add_argument("--label", default="candidate")
    run.add_argument("--run-id")
    run.add_argument("--output", required=True)
    run.add_argument("--case-id", action="append")
    run.add_argument(
        "--category",
        action="append",
        choices=("text", "image", "ambiguous", "adversarial", "plausible_wrong"),
    )
    run.add_argument("--modality", action="append", choices=("text", "image"))
    run.add_argument("--tutor-mode", action="append", choices=("hint_only", "step_by_step", "check_my_work"))
    run.set_defaults(handler=command_run)

    compare = subcommands.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--allow-cost-regression", action="store_true")
    compare.add_argument("--cost-exception-note")
    compare.set_defaults(handler=command_compare)

    review = subcommands.add_parser("review")
    review.add_argument("--report", required=True)
    review.add_argument("--review-file", required=True)
    review.add_argument("--output", required=True)
    review.set_defaults(handler=command_review)

    review_template = subcommands.add_parser("review-template")
    review_template.add_argument("--report", required=True)
    review_template.add_argument("--output", required=True)
    review_template.set_defaults(handler=command_review_template)

    promote = subcommands.add_parser("promote")
    promote.add_argument("--report", required=True)
    promote.add_argument("--destination", required=True)
    promote.add_argument("--reviewer", required=True)
    promote.add_argument("--note", required=True)
    promote.set_defaults(handler=command_promote)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.handler(args)
    except (DatasetValidationError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
