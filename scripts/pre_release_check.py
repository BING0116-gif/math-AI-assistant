"""Run the release checks locally or in CI.

The checks are deliberately fail-fast: a missing tool, unavailable network
dependency, or failed command is an error and never becomes a warning.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print(f"[pre-release] {label}: {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, cwd=cwd, check=False, env=env)
    except OSError as exc:
        raise SystemExit(f"[pre-release] FAIL {label}: cannot execute command: {exc}") from exc
    if completed.returncode:
        raise SystemExit(f"[pre-release] FAIL {label}: exit code {completed.returncode}")


def check_configuration() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    problems: list[str] = []
    if re.search(r"GF_SECURITY_ADMIN_PASSWORD:\s*\$\{[^}]*:-admin\}", compose):
        problems.append("docker-compose.yml uses the dangerous Grafana password default 'admin'")
    if re.search(r"^ADMIN_PASSWORD=change_me", example, re.MULTILINE):
        problems.append(".env.example contains the placeholder admin password change_me")
    if os.environ.get("APP_ENV") == "production" and os.environ.get("DEBUG", "false").lower() == "true":
        problems.append("DEBUG=true is forbidden when APP_ENV=production")
    if problems:
        raise SystemExit("[pre-release] FAIL configuration:\n  - " + "\n  - ".join(problems))
    print("[pre-release] PASS configuration")


def check_pinned_images() -> None:
    files = [ROOT / "Dockerfile", ROOT / "layout_worker" / "Dockerfile", ROOT / "docker-compose.yml"]
    floating: list[str] = []
    for path in files:
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"(?:^FROM\s+|\bimage:\s*)([^\s]+)", line)
            if match and (":" not in match.group(1) or match.group(1).endswith(":latest")):
                floating.append(f"{path.relative_to(ROOT)}:{number} ({match.group(1)})")
    if floating:
        raise SystemExit("[pre-release] FAIL floating core images:\n  - " + "\n  - ".join(floating))
    print("[pre-release] PASS pinned core images")


def main() -> int:
    parser = argparse.ArgumentParser(description="Math AI Assistant release gate")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-compose", action="store_true")
    args = parser.parse_args()

    check_configuration()
    check_pinned_images()
    run("Python compile", [sys.executable, "-m", "compileall", "-q", "app", "agent_core", "tools", "scripts"])
    run("affected pytest", [sys.executable, "-m", "pytest", "tests/test_phase3_migration.py", "tests/test_question_templates.py::test_migration_chain_upgrades_clean_sqlite", "tests/test_alembic_logging_hygiene.py", "-q"])
    run("Alembic heads", [sys.executable, "-m", "alembic", "-c", "app/data/alembic.ini", "heads"])
    # `alembic check` requires an up-to-date database. Use a disposable SQLite
    # database so the gate never reads or mutates data/math_ai.db.
    with tempfile.TemporaryDirectory(prefix="mathai-release-") as temp_dir:
        migration_env = os.environ.copy()
        migration_env["DATABASE_URL"] = f"sqlite:///{Path(temp_dir, 'release.db').as_posix()}"
        run("Alembic upgrade (isolated)", [sys.executable, "-m", "alembic", "-c", "app/data/alembic.ini", "upgrade", "head"], env=migration_env)
        run("Alembic check", [sys.executable, "-m", "alembic", "-c", "app/data/alembic.ini", "check"], env=migration_env)
    if not args.skip_frontend:
        run("frontend npm test", ["npm", "test", "--", "--run"], ROOT / "frontend")
        run("frontend build", ["npm", "run", "build"], ROOT / "frontend")
    if not args.skip_compose:
        run("docker compose config", ["docker", "compose", "config"])
    print("[pre-release] ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
