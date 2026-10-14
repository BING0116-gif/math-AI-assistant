"""Validate the Task 2.1 golden-case registry without model or production access."""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import yaml
# Running from scripts/ would shadow the repository package with model_quality_eval.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_quality_eval.dataset import load_v2_dataset, DatasetValidationError

REQUIRED = ("expected_capability", "key_answer", "allowed_variants", "severe_errors")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]|bearer\s+|api[_-]?key|password|token|@gmail\.com|\b1[3-9]\d{9}\b)", re.I)

def _strings(value):
    if isinstance(value, str): yield value
    elif isinstance(value, dict):
        for v in value.values(): yield from _strings(v)
    elif isinstance(value, list):
        for v in value: yield from _strings(v)

def validate(root: Path) -> dict:
    manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    errors = []
    if manifest.get("schema_version") != "golden-case-registry-1.0": errors.append("unsupported schema_version")
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version): errors.append("version must be semver")
    source_root = (root / manifest["source_dataset"]).resolve()
    try: bundle = load_v2_dataset(source_root)
    except Exception as exc: raise DatasetValidationError(f"source dataset invalid: {exc}") from exc
    by_id = bundle.by_id
    expanded = []
    for capability, spec in (manifest.get("categories") or {}).items():
        prefixes = spec.get("include", [])
        selected = [case for case in bundle.cases if any(case.id.startswith(p) for p in prefixes)]
        minimum = spec.get("min_samples", 0)
        if len(selected) < minimum: errors.append(f"{capability}: {len(selected)} samples, minimum {minimum}")
        for case in selected:
            item = {"case_id": case.id, "capability": capability, "input": {"question": case.question, "modality": case.modality},
                    "expected_capability": spec.get("expected_capability"), "key_answer": {"source_oracle": case.oracle.model_dump(mode="json"), "policy": spec.get("key_answer")},
                    "allowed_variants": spec.get("allowed_variants"), "severe_errors": spec.get("severe_errors"),
                    "dataset_version": manifest.get("version"), "privacy": {"source": "synthetic", "redacted": True}}
            for field in REQUIRED:
                if not item.get(field): errors.append(f"{capability}/{case.id}: missing {field}")
            if case.id not in by_id: errors.append(f"unknown case id: {case.id}")
            if any(SECRET_RE.search(s) for s in _strings(case.model_dump())): errors.append(f"{capability}/{case.id}: prohibited sensitive marker")
            expanded.append(item)
    if len({x["case_id"] + ":" + x["capability"] for x in expanded}) != len(expanded): errors.append("duplicate expanded case")
    return {"status": "valid" if not errors else "invalid", "dataset_version": version, "source_dataset": str(source_root),
            "source_hash": bundle.computed_hash, "expanded_case_count": len(expanded),
            "category_counts": {k: sum(x["capability"] == k for x in expanded) for k in manifest.get("categories", {})}, "errors": errors}

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", default="evaluations/golden"); p.add_argument("--json", action="store_true"); args = p.parse_args()
    try: report = validate(Path(args.root).resolve())
    except Exception as exc: print(json.dumps({"status":"error","error":str(exc)}, ensure_ascii=False), file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"{report['status']}: {report['expanded_case_count']} expanded cases; source {report['source_hash']}")
    if report["errors"]: print("\
".join(report["errors"]), file=sys.stderr)
    return 0 if report["status"] == "valid" else 1
if __name__ == "__main__": raise SystemExit(main())




