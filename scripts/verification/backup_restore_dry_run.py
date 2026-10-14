"""Read-only backup/restore rehearsal planner.

This command never invokes pg_dump/pg_restore, deletes files, or writes a
backup. It validates configured source roots and prints the commands that an
operator would run in an isolated recovery environment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_root(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "files": 0, "bytes": 0}
    files = [p for p in path.rglob("*") if p.is_file() and not p.is_symlink()]
    return {"path": str(path), "exists": True, "files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a non-mutating backup/recovery rehearsal plan")
    parser.add_argument("--content-root", type=Path, default=Path("runtime/content"))
    parser.add_argument("--notes-root", type=Path, default=Path("runtime/notes"))
    parser.add_argument("--animations-root", type=Path, default=Path("runtime/animations"))
    args = parser.parse_args()
    report = {
        "mode": "dry-run",
        "mutations": [],
        "file_roots": [inspect_root(p) for p in (args.content_root, args.notes_root, args.animations_root)],
        "postgres_backup_command": "scripts/operations/postgres_backup_restore.ps1 -Action backup -BackupPath <isolated-backup-path>",
        "postgres_verify_command": "scripts/operations/postgres_backup_restore.ps1 -Action verify -BackupPath <backup> -RestoreDatabase <isolated-db>",
        "qdrant_rebuild_command": "python scripts/verification/qdrant_reconcile.py --kind question --execute",
        "memory_rebuild_command": "python scripts/verification/qdrant_reconcile.py --kind memory --user-id <user-id> --execute",
        "post_restore_checks": [
            "python scripts/verification/qdrant_reconcile.py --kind question",
            "python scripts/verification/qdrant_reconcile.py --kind memory --user-id <user-id>",
            "python scripts/operations/reconcile_note_storage.py",
            "python scripts/operations/recovery.py redis-recover --user-id <user-id>",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
