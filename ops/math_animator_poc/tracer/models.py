"""Strict, dependency-free input model for the local template tracer."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


MAX_SPEC_BYTES = 4096


class SpecValidationError(ValueError):
    """Raised when an animation spec is outside the trusted contract."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SpecValidationError(f"duplicate JSON field: {key!r}")
        value[key] = item
    return value


@dataclass(frozen=True)
class MathAnimationSpec:
    """Versioned selector for a reviewed template; never contains source code."""

    schema_version: int
    template_id: str
    parameters: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MathAnimationSpec":
        if not isinstance(value, Mapping):
            raise SpecValidationError("spec must be a JSON object")

        expected = {"schema_version", "template_id", "parameters"}
        unknown = set(value) - expected
        missing = expected - set(value)
        if unknown or missing:
            raise SpecValidationError(
                f"spec fields mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise SpecValidationError("schema_version must be integer 1")
        if not isinstance(value["template_id"], str) or not value["template_id"]:
            raise SpecValidationError("template_id must be a non-empty string")
        if len(value["template_id"]) > 64:
            raise SpecValidationError("template_id exceeds 64 characters")
        if not isinstance(value["parameters"], Mapping):
            raise SpecValidationError("parameters must be a JSON object")
        if any(not isinstance(key, str) for key in value["parameters"]):
            raise SpecValidationError("parameter names must be strings")

        spec = cls(
            schema_version=1,
            template_id=value["template_id"],
            parameters=dict(value["parameters"]),
        )
        if len(spec.canonical_bytes()) > MAX_SPEC_BYTES:
            raise SpecValidationError(f"canonical spec exceeds {MAX_SPEC_BYTES} bytes")
        return spec

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "MathAnimationSpec":
        if len(raw) > MAX_SPEC_BYTES:
            raise SpecValidationError(f"spec exceeds {MAX_SPEC_BYTES} bytes")
        try:
            value = json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpecValidationError("spec is not valid UTF-8 JSON") from exc
        return cls.from_mapping(value)

    def canonical_bytes(self) -> bytes:
        try:
            text = json.dumps(
                {
                    "parameters": self.parameters,
                    "schema_version": self.schema_version,
                    "template_id": self.template_id,
                },
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise SpecValidationError("parameters must contain finite JSON values only") from exc
        return text.encode("utf-8")
