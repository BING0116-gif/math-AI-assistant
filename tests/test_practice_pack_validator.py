import json
import subprocess
import sys
from pathlib import Path


PACK = Path("evaluations/content/phase3/mean_value_fermat.yaml")


def test_fermat_vertical_slice_is_valid_and_draft_only():
    result = subprocess.run(
        [sys.executable, "scripts/validate_practice_pack.py", "--pack", str(PACK), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "valid"
    assert report["item_count"] == 3
    assert set(report["levels"]) == {"基础", "常规", "进阶"}


def test_validator_rejects_published_pack(tmp_path):
    content = PACK.read_text(encoding="utf-8").replace("review_status: draft", "review_status: published")
    path = tmp_path / "published.yaml"
    path.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/validate_practice_pack.py", "--pack", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "new pack must remain draft" in result.stderr
