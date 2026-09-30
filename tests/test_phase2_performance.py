import json
import subprocess
import sys
from pathlib import Path


def test_phase2_smoke_report_is_versioned_complete_and_network_free(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "phase2-smoke.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "performance" / "phase2_benchmark.py"),
            "--samples",
            "5",
            "--output",
            str(output),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["scenario_version"] == "phase2-v1"
    assert report["environment"]["model"] == "disabled"
    assert report["external_model_limits"] == {
        "max_calls": 3,
        "timeout_seconds": 20,
        "max_budget_usd": 0.10,
        "calls_used": 0,
    }
    names = {item["name"] for item in report["measurements"]}
    assert names == {
        "home_dependencies",
        "knowledge_catalog",
        "learning_dashboard",
        "error_book_list",
        "practice_create",
        "practice_submit",
        "rag_embedding",
        "rag_retrieval",
        "outbox_batch_50",
        "chat_stream_entry",
    }
    for item in report["measurements"]:
        assert item["samples"] == 5
        assert item["errors"] == 0
        assert item["p50_ms"] <= item["p95_ms"] <= item["p99_ms"]
        assert item["throughput_per_second"] > 0
    rag = next(item for item in report["measurements"] if item["name"] == "rag_retrieval")
    assert rag["quality"] == {"recall_at_5": 1.0, "mrr_at_5": 1.0}
    assert report["outbox"]["drained_events"] == 500
    assert report["outbox"]["pending"] == 0
    assert report["outbox"]["dead"] == 0
    assert report["passed"] is True
