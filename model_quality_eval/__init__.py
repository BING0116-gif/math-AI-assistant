"""Offline-first model-quality evaluation utilities for the Math AI Tutor."""

from .dataset import DatasetBundle, DatasetValidationError, load_dataset
from .schema import EvaluationCase, Manifest

__all__ = [
    "DatasetBundle",
    "DatasetValidationError",
    "EvaluationCase",
    "Manifest",
    "load_dataset",
]
