from collections import Counter
import json
from pathlib import Path

import pytest

from model_quality_eval.dataset import DatasetValidationError, dataset_schema, load_dataset, report_schema


DATASET = Path("evaluations/model_quality/v1")


def test_v1_dataset_is_hash_locked_approved_and_has_exact_matrix():
    bundle = load_dataset(DATASET)
    assert len(bundle.cases) == 60
    assert Counter(case.primary_category.value for case in bundle.cases) == {
        "text": 20,
        "image": 12,
        "ambiguous": 8,
        "adversarial": 10,
        "plausible_wrong": 10,
    }
    assert Counter(case.tutor_mode.value for case in bundle.cases) == {
        "hint_only": 20,
        "step_by_step": 20,
        "check_my_work": 20,
    }
    assert all(case.status == "approved" for case in bundle.cases)
    assert all(case.gold.author != case.gold.reviewer for case in bundle.cases)
    assert bundle.computed_hash == bundle.manifest.dataset_hash
    assert len(bundle.schema_hash) == 64
    assert set(bundle.case_hashes) == {case.case_id for case in bundle.cases}
    assert all(len(value) == 64 for value in bundle.case_hashes.values())


def test_v1_dataset_meets_cross_cutting_minimums_and_uses_only_synthetic_images():
    bundle = load_dataset(DATASET)
    assert sum(bool(case.tool_expectation.required_tools or case.tool_expectation.forbidden_tools) for case in bundle.cases) >= 15
    assert sum(case.retrieval_expectation.required for case in bundle.cases) >= 12
    assert sum(bool(case.safety_expectation.protected_canaries) for case in bundle.cases) >= 10
    assert sum(case.ai_offline_case for case in bundle.cases) >= 8
    image_cases = [case for case in bundle.cases if case.modality == "image"]
    assert len(image_cases) == 12
    assert all("synthetic-image" in case.tags for case in image_cases)
    assert all((DATASET / case.input.image_asset).is_file() for case in image_cases)


def test_committed_case_and_report_json_schemas_match_runtime_contracts():
    schema_root = DATASET.parent / "schema"
    assert json.loads((schema_root / "case.schema.json").read_text(encoding="utf-8")) == dataset_schema()
    assert json.loads((schema_root / "report.schema.json").read_text(encoding="utf-8")) == report_schema()


def test_dataset_rejects_manifest_hash_drift(tmp_path):
    source = DATASET / "manifest.yaml"
    target = tmp_path / "manifest.yaml"
    target.write_text(source.read_text(encoding="utf-8").replace("title:", "title: changed-", 1), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="dataset hash mismatch|missing"):
        load_dataset(tmp_path)


def test_case_files_do_not_contain_absolute_paths_or_real_contact_data():
    bundle = load_dataset(DATASET)
    for case in bundle.cases:
        raw = (DATASET / bundle.manifest.cases[[item.case_id for item in bundle.manifest.cases].index(case.case_id)].path).read_text(encoding="utf-8")
        assert "C:\\" not in raw
        assert "@qq.com" not in raw
        assert "@gmail.com" not in raw
        assert "sk-" not in raw
