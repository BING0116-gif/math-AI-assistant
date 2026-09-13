"""Local-only T15 MathAnimator tracer."""

from .models import MathAnimationSpec, SpecValidationError
from .runner import LocalTracerRunner, RenderResult

__all__ = [
    "LocalTracerRunner",
    "MathAnimationSpec",
    "RenderResult",
    "SpecValidationError",
]
