"""Validate a reviewed-before-publish practice content pack."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
import yaml

LEVELS = {"基础", "常规", "进阶"}
TYPES = {"choice", "judge", "numeric_fill", "expression_fill"}
STATUSES = {"draft", "reviewed", "verified", "pending"}

def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", "", text or "").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def validate(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = []
    required = ("version", "chapter_code", "knowledge_point_code", "source", "review_status", "verification_status", "privacy", "items")
    for key in required:
        if not payload.get(key): errors.append(f"missing {key}")
    if payload.get("privacy") != "synthetic": errors.append("privacy must be synthetic")
    if payload.get("review_status") != "draft": errors.append("new pack must remain draft")
    items = payload.get("items")
    if not isinstance(items, list) or not items: errors.append("items must be non-empty")
    ids, fingerprints = set(), set()
    levels = set()
    for item in items or []:
        for key in ("id", "level", "difficulty", "question_type", "content", "answer", "answer_spec", "analysis", "knowledge_point_codes", "source", "verification_status"):
            if item.get(key) in (None, "", []): errors.append(f"{item.get('id', '?')}: missing {key}")
        item_id = str(item.get("id", ""))
        if item_id in ids: errors.append(f"duplicate id: {item_id}")
        ids.add(item_id)
        fp = _fingerprint(str(item.get("content", "")))
        if fp in fingerprints: errors.append(f"duplicate question: {item_id}")
        fingerprints.add(fp)
        level = item.get("level"); levels.add(level)
        if level not in LEVELS: errors.append(f"{item_id}: invalid level")
        if not isinstance(item.get("difficulty"), int) or not 1 <= item["difficulty"] <= 5: errors.append(f"{item_id}: invalid difficulty")
        if item.get("question_type") not in TYPES: errors.append(f"{item_id}: unsupported question_type")
        if payload.get("knowledge_point_code") not in (item.get("knowledge_point_codes") or []): errors.append(f"{item_id}: knowledge point mismatch")
        if item.get("source") != payload.get("source") and not item.get("source"): errors.append(f"{item_id}: missing source")
        if item.get("verification_status") != "verified": errors.append(f"{item_id}: answer not verified")
        spec = item.get("answer_spec") or {}
        if item.get("question_type") == "choice":
            option_ids = {str(option.get("id")) for option in item.get("options") or [] if isinstance(option, dict)}
            if len(option_ids) < 2 or spec.get("kind") != "choice" or str(spec.get("correct")) not in option_ids or str(item.get("answer")) != str(spec.get("correct")):
                errors.append(f"{item_id}: invalid choice answer contract")
        elif item.get("question_type") == "judge":
            if spec.get("kind") != "judge" or not isinstance(spec.get("correct"), bool) or ((spec["correct"] and item.get("answer") != "正确") or (not spec["correct"] and item.get("answer") != "错误")):
                errors.append(f"{item_id}: invalid judge answer contract")
        elif item.get("question_type") == "numeric_fill":
            value = spec.get("value")
            if spec.get("kind") != "numeric_fill" or not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{item_id}: invalid numeric answer contract")
            elif str(item.get("answer")).strip() != str(value):
                errors.append(f"{item_id}: answer does not match numeric oracle")
        elif spec.get("version") != 1: errors.append(f"{item_id}: answer_spec version must be 1")
    for level in LEVELS:
        if level not in levels: errors.append(f"missing level: {level}")
    return {"status": "valid" if not errors else "invalid", "pack": str(path), "item_count": len(items or []), "levels": sorted(levels), "errors": errors}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--pack", required=True); parser.add_argument("--json", action="store_true"); args = parser.parse_args()
    try: report = validate(Path(args.pack))
    except Exception as exc: print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr); return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"{report['status']}: {report['item_count']} items")
    if report["errors"]: print("\n".join(report["errors"]), file=sys.stderr)
    return 0 if report["status"] == "valid" else 1
if __name__ == "__main__": raise SystemExit(main())
