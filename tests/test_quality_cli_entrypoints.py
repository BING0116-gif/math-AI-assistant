import json
import subprocess
import sys
from pathlib import Path

import yaml


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
    # 用例数不写硬编码字面量：1-E 把矩阵从 61 扩到 95 后，写死的数字立刻变成
    # 假失败。manifest 是数据集的声明源，这里拿它跟 CLI 实际计数对撞，
    # 既能校验配额与条数一致，也能抓住“用例文件被删但 manifest 未同步”的反向漂移。
    manifest = yaml.safe_load(
        (ROOT / "evaluations" / "model_quality" / "v2" / "manifest.yaml").read_text(encoding="utf-8")
    )
    expected = len(manifest["cases"])
    assert expected == sum(manifest["category_quotas"].values())
    assert payload["case_count"] == expected
    # 真实不变量：全部用例都必须在离线安全模式下跑完，零线上模型调用。
    assert payload["offline_case_count"] == payload["case_count"]
    assert payload["live_calls"] == 0
    assert payload["model_quality_claim"] is False
