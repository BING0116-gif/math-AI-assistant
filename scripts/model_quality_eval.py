"""CLI for validating, executing, comparing, and promoting Phase 4 evaluations."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Direct execution puts ``scripts/`` before the repository root on sys.path,
# causing this file to shadow the sibling ``model_quality_eval`` package.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_quality_eval.dataset import DatasetValidationError, load_dataset, load_v2_case, load_v2_dataset
from model_quality_eval.v2_runner import compare_v2_reports, run_mocked_v2
from model_quality_eval.gates import load_gates
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


def command_validate_gates(args) -> int:
    gates = load_gates(args.gates)
    print(json.dumps({
        "status": "valid",
        "schema_version": gates.schema_version,
        "blocking": gates.blocking.model_dump(mode="json"),
        "observatory": gates.observatory.model_dump(mode="json"),
    }, ensure_ascii=False))
    return 0


def command_validate_case(args) -> int:
    if args.schema_version != "2.0":
        raise ValueError("validate-case currently supports schema version 2.0 only")
    case = load_v2_case(args.case)
    print(json.dumps({
        "status": "valid",
        "schema_version": args.schema_version,
        "case_id": case.id,
        "category": case.category,
    }, ensure_ascii=False))
    return 0


def command_validate_v2(args) -> int:
    bundle = load_v2_dataset(args.dataset)
    print(json.dumps({
        "status": "valid",
        "dataset_version": bundle.manifest.dataset_version,
        "dataset_hash": bundle.computed_hash,
        "case_count": len(bundle.cases),
        "categories": {name: count for name, count in sorted(bundle.manifest.category_quotas.items()) if count},
    }, ensure_ascii=False))
    return 0


def command_audit_v2(args) -> int:
    """Audit the v2 matrix without calling a model or application services."""
    bundle = load_v2_dataset(args.dataset)
    offline_cases = [case for case in bundle.cases if case.ai_offline_case]
    missing_offline = [case.id for case in bundle.cases if not case.ai_offline_case]
    category_counts = {}
    for case in bundle.cases:
        category_counts[case.category] = category_counts.get(case.category, 0) + 1
    contract_complete = all(
        case.oracle.answer_match.mode
        and (case.category != "retrieval" or case.retrieval_expectation is not None)
        and (case.category != "tool_failure" or case.tool_failure_plan is not None)
        for case in bundle.cases
    )
    if missing_offline or not contract_complete:
        raise DatasetValidationError(
            "v2 offline audit failed: every case must be ai_offline_case and have a complete oracle contract"
        )
    print(json.dumps({
        "status": "offline_safe",
        "dataset_version": bundle.manifest.dataset_version,
        "dataset_hash": bundle.computed_hash,
        "case_count": len(bundle.cases),
        "offline_case_count": len(offline_cases),
        "categories": {name: count for name, count in sorted(category_counts.items())},
        "live_calls": 0,
        "model_quality_claim": False,
    }, ensure_ascii=False))
    return 0

def command_run_v2(args) -> int:
    bundle = load_v2_dataset(args.dataset)
    selected = None
    if args.case_id:
        by_id = bundle.by_id
        missing = [cid for cid in args.case_id if cid not in by_id]
        if missing:
            print(json.dumps({"status": "error", "error": f"unknown case ids: {missing}"}, ensure_ascii=False))
            return 1
        selected = [by_id[cid] for cid in args.case_id]
    run_id = args.run_id or new_run_id(args.label)
    report = run_mocked_v2(bundle, run_id=run_id, label=args.label, selected=selected)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "v2_results.json", report)
    print(json.dumps({
        "run_id": run_id,
        "mode": "mocked",
        "dataset_hash": report["dataset_hash"],
        "summary": report["summary"],
        "output": str(output.resolve()),
    }, ensure_ascii=False))
    return 0


def command_compare_v2(args) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    gates = load_gates(args.gates)
    verdict = compare_v2_reports(baseline, candidate, gates)
    print(json.dumps(verdict, ensure_ascii=False))
    return 0 if verdict["status"] == "approved" else 2




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
    gates = load_gates(args.gates) if args.gates else None
    comparison = compare_reports(
        baseline,
        candidate,
        allow_cost_regression=args.allow_cost_regression,
        cost_exception_note=args.cost_exception_note,
        gates=gates,
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
    parser = argparse.ArgumentParser(description="Phase 4 model quality evaluation")
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("--dataset", required=True)
    validate.set_defaults(handler=command_validate)

    validate_gates = subcommands.add_parser("validate-gates")
    validate_gates.add_argument("--gates", required=True)
    validate_gates.set_defaults(handler=command_validate_gates)

    validate_case = subcommands.add_parser("validate-case")
    validate_case.add_argument("--schema-version", required=True)
    validate_case.add_argument("--case", required=True)
    validate_case.set_defaults(handler=command_validate_case)

    validate_v2 = subcommands.add_parser("validate-v2")
    validate_v2.add_argument("--dataset", required=True)
    validate_v2.set_defaults(handler=command_validate_v2)

    audit_v2 = subcommands.add_parser("audit-v2")
    audit_v2.add_argument("--dataset", required=True)
    audit_v2.set_defaults(handler=command_audit_v2)

    run_v2 = subcommands.add_parser("run-v2", help="Deterministic mocked run over a v2 dataset (no model calls)")
    run_v2.add_argument("--dataset", required=True)
    run_v2.add_argument("--label", default="candidate")
    run_v2.add_argument("--run-id")
    run_v2.add_argument("--output", required=True)
    run_v2.add_argument("--case-id", action="append")
    run_v2.set_defaults(handler=command_run_v2)

    compare_v2 = subcommands.add_parser("compare-v2", help="Gate verdict between two v2 mocked/live reports")
    compare_v2.add_argument("--baseline", required=True)
    compare_v2.add_argument("--candidate", required=True)
    compare_v2.add_argument("--gates", required=True)
    compare_v2.set_defaults(handler=command_compare_v2)

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
    compare.add_argument("--gates", help="versioned YAML quality-gate configuration")
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
