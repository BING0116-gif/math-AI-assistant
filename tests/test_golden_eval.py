import json
import subprocess
import sys
from pathlib import Path


def test_golden_registry_validates_and_reuses_v2():
    result = subprocess.run(
        [sys.executable, "scripts/validate_golden_eval.py", "--json"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "valid"
    assert report["expanded_case_count"] >= 35
    assert set(report["category_counts"]) == {
        "math_qa", "image_question", "formula_parsing", "rag_retrieval",
        "error_attribution", "learning_recommendation", "refusal",
    }
    assert report["source_hash"]
