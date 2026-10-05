from pathlib import Path
import json
import subprocess
import sys

import pytest

from model_quality_eval.dataset import DatasetValidationError, load_v2_case, load_v2_dataset, v2_case_schema, v2_manifest_schema
from model_quality_eval.v2_schema import V2Case


def _case(**overrides):
    payload = {
        "id": "mq-v2-adv-014",
        "category": "advanced_proof",
        "modality": "text",
        "tutor_mode": "solve",
        "question": "证明一个二阶导数下界。",
        "requirements": ["给出闭合推导", "说明取等条件"],
        "oracle": {
            "answer_match": {"mode": "expression", "expected": "f''(xi) >= 8"},
            "key_steps": [{"text": "极值点处取值", "weight": 1}, {"text": "二阶展开", "weight": 2}],
            "allowed_expressions": ["泰勒"],
            "forbidden_claims": ["f 是三次多项式"],
        },
        "critic_expectation": {"verdict": "pass", "must_check": ["answered_question", "derivation_closed", "no_gap"]},
        "user_fixture": "eval_standard_user",
        "ai_offline_case": False,
    }
    payload.update(overrides)
    return payload


def test_v2_schema_accepts_weighted_steps_and_critic_expectation():
    case = V2Case.model_validate(_case())
    assert case.category == "advanced_proof"
    assert case.oracle.key_steps[1].weight == 2
    assert case.critic_expectation.verdict == "pass"
    assert "V2CriticExpectation" in str(v2_case_schema())
    assert "V2ManifestCaseRef" in str(v2_manifest_schema())


@pytest.mark.parametrize(
    "payload,error",
    [
        (_case(category="vision", modality="text"), "vision cases must use image modality"),
        (_case(category="tool_failure"), "tool_failure cases require tool_failure_plan"),
        (_case(category="retrieval"), "retrieval cases require retrieval_expectation"),
    ],
)
def test_v2_category_specific_requirements_are_enforced(payload, error):
    with pytest.raises(ValueError, match=error):
        V2Case.model_validate(payload)


def test_v2_case_loader_applies_sensitive_content_guard(tmp_path: Path):
    case_path = tmp_path / "case.yaml"
    case_path.write_text("question: contact test@example.com\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="possible email"):
        load_v2_case(case_path)


def test_validate_case_cli_accepts_v2_fixture(tmp_path: Path):
    case_path = tmp_path / "case.yaml"
    import yaml

    case_path.write_text(yaml.safe_dump(_case(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.model_quality_eval", "validate-case", "--schema-version", "2.0", "--case", str(case_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload == {"status": "valid", "schema_version": "2.0", "case_id": "mq-v2-adv-014", "category": "advanced_proof"}


def test_committed_v2_representative_matrix_is_hash_locked():
    bundle = load_v2_dataset(Path("evaluations/model_quality/v2"))
    assert len(bundle.cases) == 61
    assert set(bundle.by_id) == {item.case_id for item in bundle.manifest.cases}
    assert bundle.manifest.category_quotas["tool_failure"] == 10
    assert bundle.manifest.category_quotas["security"] == 10
    assert bundle.manifest.category_quotas["retrieval"] == 10
    assert bundle.manifest.category_quotas["basic"] == 10
    assert all(count == 7 for name, count in bundle.manifest.category_quotas.items() if name not in {"tool_failure", "security", "retrieval", "basic"})
    assert {case.category for case in bundle.cases} == {
        "basic", "advanced_proof", "multi_turn", "vision", "retrieval", "tool_failure", "security"
    }
