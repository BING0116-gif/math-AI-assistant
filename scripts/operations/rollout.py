"""Gray rollout plan and emergency rollback.

Examples:
  python scripts/operations/rollout.py --flag model_routing --percent 5 --dry-run
  python scripts/operations/rollout.py --flag model_routing --rollback --dry-run
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.feature_flags import FLAG_REGISTRY, rollback_flag

def main() -> int:
    parser = argparse.ArgumentParser(description="Math AI gray rollout (dry-run by default)")
    parser.add_argument("--flag", required=True, choices=sorted(FLAG_REGISTRY))
    parser.add_argument("--percent", type=int, choices=range(0, 101))
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print plan without changing runtime state (default)")
    parser.add_argument("--apply", action="store_true", help="apply emergency in-process rollback; requires explicit operator action")
    args = parser.parse_args()
    if args.rollback:
        result = rollback_flag(args.flag, dry_run=not args.apply)
    elif args.percent is not None:
        result = {"flag": args.flag, "planned_rollout_percent": args.percent, "dry_run": True, "data_action": "none; preserve old and new path evidence"}
    else:
        parser.error("provide --percent or --rollback")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
