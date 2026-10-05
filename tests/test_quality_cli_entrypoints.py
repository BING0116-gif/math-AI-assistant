import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_model_quality_direct_and_module_entrypoints_match():
    command = ("validate", "--dataset", "evaluations/model_quality/v1")
    direct = _run("scripts/model_quality_eval.py", *command)
    module = _run("-m", "scripts.model_quality_eval", *command)

    assert direct.returncode == module.returncode == 0
    assert json.loads(direct.stdout) == json.loads(module.stdout)
    assert json.loads(direct.stdout)["case_count"] == 60


def test_rag_quality_direct_and_module_entrypoints_are_importable():
    direct = _run("scripts/rag_quality_eval.py", "--help")
    module = _run("-m", "scripts.rag_quality_eval", "--help")

    assert direct.returncode == module.returncode == 0
    assert "--gold" in direct.stdout
    assert "--results" in direct.stdout
    assert "--output" in direct.stdout


def test_v2_offline_audit_never_calls_live_model():
    completed = _run(
        "-m",
        "scripts.model_quality_eval",
        "audit-v2",
        "--dataset",
        "evaluations/model_quality/v2",
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "offline_safe"
    assert payload["case_count"] == 61
    assert payload["offline_case_count"] == 61
    assert payload["live_calls"] == 0
    assert payload["model_quality_claim"] is False
