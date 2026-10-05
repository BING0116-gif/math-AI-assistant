"""Offline-first model-quality evaluation utilities for the Math AI Tutor."""

from .dataset import DatasetBundle, DatasetValidationError, load_dataset
from .schema import EvaluationCase, Manifest
from .v2_schema import EvaluationCaseV2, ManifestV2

__all__ = [
    "DatasetBundle",
    "DatasetValidationError",
    "EvaluationCase",
    "EvaluationCaseV2",
    "Manifest",
    "ManifestV2",
    "load_dataset",
]
