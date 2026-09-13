"""Closed registry mapping public template ids to reviewed local scenes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping

from .models import MathAnimationSpec, SpecValidationError


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    source_name: str
    scene_name: str
    output_relative_path: str
    source_sha256: str
    allowed_parameters: frozenset[str] = frozenset()

    @property
    def source_path(self) -> Path:
        return SOURCE_ROOT / self.source_name


TEMPLATES: Mapping[str, TemplateDefinition] = {
    "secant_to_tangent": TemplateDefinition(
        template_id="secant_to_tangent",
        source_name="secant_to_tangent.py",
        scene_name="SecantToTangent",
        output_relative_path="videos/scene/480p15/SecantToTangent.mp4",
        source_sha256="8E0AFC1A637A4D4CD17D689DBB6DBEB676312BD1F88627019AC81B129CF7E2FD",
    ),
    "riemann_sum": TemplateDefinition(
        template_id="riemann_sum",
        source_name="study_scenes.py",
        scene_name="RiemannSumApproximation",
        output_relative_path="videos/scene/480p15/RiemannSumApproximation.mp4",
        source_sha256="2AC4B3F9B1EEEAAFE10D00A3F189CD5A70AA5D47E1E98458ED47E55ACA6DA4D0",
    ),
    "taylor_approximation": TemplateDefinition(
        template_id="taylor_approximation",
        source_name="study_scenes.py",
        scene_name="TaylorApproximation",
        output_relative_path="videos/scene/480p15/TaylorApproximation.mp4",
        source_sha256="2AC4B3F9B1EEEAAFE10D00A3F189CD5A70AA5D47E1E98458ED47E55ACA6DA4D0",
    ),
}


def resolve_template(spec: MathAnimationSpec) -> TemplateDefinition:
    definition = TEMPLATES.get(spec.template_id)
    if definition is None:
        raise SpecValidationError(f"unknown template_id: {spec.template_id!r}")

    unknown_parameters = set(spec.parameters) - definition.allowed_parameters
    missing_parameters = definition.allowed_parameters - set(spec.parameters)
    if unknown_parameters or missing_parameters:
        raise SpecValidationError(
            "template parameters mismatch: "
            f"missing={sorted(missing_parameters)}, unknown={sorted(unknown_parameters)}"
        )
    return definition


def verify_trusted_source(definition: TemplateDefinition) -> str:
    source_path = definition.source_path.resolve()
    if source_path.parent != SOURCE_ROOT.resolve() or not source_path.is_file():
        raise SpecValidationError("trusted template source is missing or outside source root")
    actual = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
    if actual != definition.source_sha256:
        raise SpecValidationError(
            f"trusted template source hash mismatch for {definition.source_name}"
        )
    return actual
