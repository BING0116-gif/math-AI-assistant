"""Adapter from verified T08 MathVisualSpec data to fixed animation templates."""

from __future__ import annotations

import math
from typing import Any, Mapping

from app.services.math_visualizer import MathVisualValidationError, MathVisualizer

from .models import MathAnimationSpec, SpecValidationError


class VisualAdapterError(SpecValidationError):
    """The T08 visual is valid, but does not exactly match a trusted template."""


def adapt_math_visual_spec(
    raw_visual_spec: Mapping[str, Any],
    requested_template_id: str,
) -> MathAnimationSpec:
    """Validate through T08 first, then require exact fixed-template semantics."""
    try:
        cleaned = MathVisualizer().visualize(raw_visual_spec)
    except MathVisualValidationError as exc:
        raise VisualAdapterError(f"T08 visual validation failed: {exc}") from exc

    if cleaned["visualization_status"] != "ok":
        raise VisualAdapterError("partial T08 visuals cannot drive an animation template")
    verification = cleaned.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "verified":
        raise VisualAdapterError("animation template requires MathVerifier-backed T08 data")

    if requested_template_id == "secant_to_tangent":
        _require_secant_contract(raw_visual_spec, cleaned["spec"])
    elif requested_template_id == "riemann_sum":
        _require_riemann_contract(raw_visual_spec, cleaned["spec"])
    elif requested_template_id == "taylor_approximation":
        raise VisualAdapterError(
            "T08 has no verified Taylor-polynomial sequence contract; direct mapping is disabled"
        )
    else:
        raise VisualAdapterError(f"template is not T08-adaptable: {requested_template_id!r}")

    return MathAnimationSpec.from_mapping(
        {
            "schema_version": 1,
            "template_id": requested_template_id,
            "parameters": {},
        }
    )


def _require_secant_contract(raw: Mapping[str, Any], cleaned: Mapping[str, Any]) -> None:
    if cleaned.get("type") != "tangent_line":
        raise VisualAdapterError("secant template requires T08 type tangent_line")
    request = raw.get("verification_request")
    values = raw.get("verified_values")
    if not isinstance(request, Mapping) or not isinstance(values, Mapping):
        raise VisualAdapterError("secant template requires verifier request and values")
    if (
        _compact(request.get("expression")) != "x**2"
        or _compact(request.get("derivative", request.get("claimed"))) != "2*x"
        or str(request.get("variable") or "x") != "x"
        or not _close(values.get("tangent_x"), 1.0)
        or not _close(values.get("tangent_y"), 1.0)
        or not _close(values.get("slope"), 2.0)
    ):
        raise VisualAdapterError("T08 tangent data does not match fixed y=x^2 at x=1 template")


def _require_riemann_contract(raw: Mapping[str, Any], cleaned: Mapping[str, Any]) -> None:
    if cleaned.get("type") != "area_under_curve":
        raise VisualAdapterError("Riemann template requires T08 type area_under_curve")
    request = raw.get("verification_request")
    if not isinstance(request, Mapping):
        raise VisualAdapterError("Riemann template requires an integral verification request")
    if (
        request.get("type") != "integral"
        or _compact(request.get("expression")) != "x**2"
        or str(request.get("variable") or "x") != "x"
        or not _close(request.get("lower"), 0.0)
        or not _close(request.get("upper"), 2.0)
        or not _close(request.get("claimed"), 8.0 / 3.0)
    ):
        raise VisualAdapterError("T08 integral data does not match fixed y=x^2 on [0,2] template")


def _compact(value: Any) -> str:
    return "".join(str(value or "").split())


def _close(value: Any, expected: float) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and math.isclose(number, expected, rel_tol=1e-9, abs_tol=1e-9)
