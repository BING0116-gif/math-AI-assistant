"""Dataset loading, hashing, quota checks, and sensitive-data guards."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from PIL import Image, UnidentifiedImageError

from .schema import EvaluationCase, Manifest, PrimaryCategory, RunReport


class DatasetValidationError(ValueError):
    pass


SENSITIVE_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "secret": re.compile(r"(?i)(sk-[A-Za-z0-9_-]{16,}|bearer\s+[A-Za-z0-9._-]{16,})"),
    "windows_absolute_path": re.compile(r"(?i)\b[A-Z]:\\"),
}


@dataclass(frozen=True)
class DatasetBundle:
    root: Path
    manifest: Manifest
    cases: tuple[EvaluationCase, ...]
    computed_hash: str
    schema_hash: str
    case_hashes: dict[str, str]

    @property
    def by_id(self) -> dict[str, EvaluationCase]:
        return {case.case_id: case for case in self.cases}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DatasetValidationError(f"expected mapping in {path}")
    return data


def compute_dataset_hash(root: Path, manifest_data: dict[str, Any]) -> str:
    canonical_manifest = dict(manifest_data)
    canonical_manifest.pop("dataset_hash", None)
    digest = hashlib.sha256(
        json.dumps(canonical_manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    for ref in sorted(manifest_data.get("cases", []), key=lambda item: item["case_id"]):
        case_path = root / PurePosixPath(ref["path"])
        digest.update(case_path.read_bytes())
        case_data = _load_yaml(case_path)
        asset = (case_data.get("input") or {}).get("image_asset")
        if asset:
            digest.update((root / PurePosixPath(asset)).read_bytes())
    return digest.hexdigest()


def _validate_sensitive_content(case_path: Path, raw_text: str) -> None:
    for name, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(raw_text):
            raise DatasetValidationError(f"{case_path}: possible {name} detected")


def _validate_asset(root: Path, case: EvaluationCase) -> None:
    if not case.input.image_asset:
        return
    asset_ref = PurePosixPath(case.input.image_asset)
    if asset_ref.is_absolute() or ".." in asset_ref.parts:
        raise DatasetValidationError(f"{case.case_id}: unsafe image asset path")
    path = root / asset_ref
    if not path.is_file():
        raise DatasetValidationError(f"{case.case_id}: missing image asset {asset_ref}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != case.input.image_sha256:
        raise DatasetValidationError(f"{case.case_id}: image SHA-256 mismatch")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise DatasetValidationError(f"{case.case_id}: unsupported image format")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise DatasetValidationError(f"{case.case_id}: image exceeds 2 MiB")
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise DatasetValidationError(f"{case.case_id}: invalid image asset") from error
    if width < 32 or height < 32 or width > 2048 or height > 2048:
        raise DatasetValidationError(f"{case.case_id}: image dimensions must be between 32 and 2048 pixels")


def _count_predicate(cases: list[EvaluationCase], predicate) -> int:
    return sum(1 for case in cases if predicate(case))


def _validate_manifest_contract(manifest: Manifest, cases: list[EvaluationCase]) -> None:
    if len(cases) != len(manifest.cases):
        raise DatasetValidationError("manifest case count does not match loaded cases")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise DatasetValidationError("duplicate case_id detected")
    manifest_ids = [ref.case_id for ref in manifest.cases]
    if ids != manifest_ids:
        raise DatasetValidationError("manifest case order/id does not match case files")
    categories = Counter(case.primary_category for case in cases)
    modes = Counter(case.tutor_mode for case in cases)
    if categories != Counter(manifest.category_quotas):
        raise DatasetValidationError(f"category quotas mismatch: {dict(categories)}")
    if modes != Counter(manifest.tutor_mode_quotas):
        raise DatasetValidationError(f"tutor mode quotas mismatch: {dict(modes)}")
    if _count_predicate(cases, lambda c: bool(c.tool_expectation.required_tools or c.tool_expectation.forbidden_tools)) < manifest.minimum_tool_cases:
        raise DatasetValidationError("tool-case minimum not met")
    if _count_predicate(cases, lambda c: c.retrieval_expectation.required) < manifest.minimum_retrieval_cases:
        raise DatasetValidationError("retrieval-case minimum not met")
    if _count_predicate(cases, lambda c: bool(c.safety_expectation.protected_canaries)) < manifest.minimum_cross_user_cases:
        raise DatasetValidationError("cross-user-case minimum not met")
    if _count_predicate(cases, lambda c: c.ai_offline_case) < manifest.minimum_ai_offline_cases:
        raise DatasetValidationError("AI-offline-case minimum not met")
    image_cases = [case for case in cases if case.primary_category == PrimaryCategory.IMAGE]
    if any(case.modality != "image" for case in image_cases):
        raise DatasetValidationError("all image-category cases must include assets")


def load_dataset(dataset_root: str | Path, *, require_approved: bool = True) -> DatasetBundle:
    root = Path(dataset_root).resolve()
    manifest_path = root / "manifest.yaml"
    if not manifest_path.is_file():
        raise DatasetValidationError(f"missing manifest: {manifest_path}")
    manifest_data = _load_yaml(manifest_path)
    manifest = Manifest.model_validate(manifest_data)
    cases: list[EvaluationCase] = []
    case_hashes: dict[str, str] = {}
    for ref in manifest.cases:
        ref_path = PurePosixPath(ref.path)
        if ref_path.is_absolute() or ".." in ref_path.parts:
            raise DatasetValidationError(f"unsafe case path: {ref.path}")
        path = root / ref_path
        if not path.is_file():
            raise DatasetValidationError(f"missing case file: {path}")
        raw_text = path.read_text(encoding="utf-8")
        _validate_sensitive_content(path, raw_text)
        case = EvaluationCase.model_validate(yaml.safe_load(raw_text))
        if case.case_id != ref.case_id:
            raise DatasetValidationError(f"case id mismatch in {path}")
        case_hashes[case.case_id] = hashlib.sha256(path.read_bytes()).hexdigest()
        if require_approved and case.status != "approved":
            raise DatasetValidationError(f"{case.case_id}: case is not approved")
        _validate_asset(root, case)
        cases.append(case)
    _validate_manifest_contract(manifest, cases)
    computed_hash = compute_dataset_hash(root, manifest_data)
    if manifest.dataset_hash != computed_hash:
        raise DatasetValidationError(
            f"dataset hash mismatch: manifest={manifest.dataset_hash}, computed={computed_hash}"
        )
    schema_path = root.parent / "schema" / "case.schema.json"
    if not schema_path.is_file():
        raise DatasetValidationError(f"missing case schema: {schema_path}")
    schema_hash = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return DatasetBundle(
        root=root,
        manifest=manifest,
        cases=tuple(cases),
        computed_hash=computed_hash,
        schema_hash=schema_hash,
        case_hashes=case_hashes,
    )


def dataset_schema() -> dict[str, Any]:
    return EvaluationCase.model_json_schema()


def report_schema() -> dict[str, Any]:
    return RunReport.model_json_schema()
