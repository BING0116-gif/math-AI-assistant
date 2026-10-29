"""Pure V2 replay plans; no application imports, database writes or model calls."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Any

from .v2_schema import V2Case


def _fixture_id(dataset_hash: str, run_id: str, case_id: str, role: str) -> str:
    raw = f"{dataset_hash}:{run_id}:{case_id}:{role}"
    return f"mq-v2-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def build_v2_replay_plan(case: V2Case, *, dataset_hash: str, run_id: str) -> dict[str, Any]:
    """Translate synthetic case data into owned sessions and ordered messages."""
    context = case.context_fixture
    conversation = context.get("conversation", [])
    if not isinstance(conversation, list):
        raise ValueError(f"{case.id}: conversation must be a list")
    messages: list[dict[str, str]] = []
    for index, item in enumerate(conversation):
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError(f"{case.id}: invalid role at conversation item {index}")
        if not isinstance(item.get("content"), str) or not item["content"].strip():
            raise ValueError(f"{case.id}: empty content at conversation item {index}")
        messages.append({"role": item["role"], "content": item["content"]})
    user_a = _fixture_id(dataset_hash, run_id, case.id, "user-a")
    user_b = _fixture_id(dataset_hash, run_id, case.id, "user-b")
    external_id = context.get("external_session_id") or _fixture_id(dataset_hash, run_id, case.id, "session")
    if not isinstance(external_id, str) or not external_id:
        raise ValueError(f"{case.id}: invalid external session id")
    other = context.get("other_user_session")
    protected_session = None
    if other is not None or (isinstance(case.user_fixture, dict) and case.user_fixture.get("cross_user")):
        if other is not None and not isinstance(other, dict):
            raise ValueError(f"{case.id}: invalid other-user session")
        other = other or {}
        protected_session = {
            "owner_id": user_b,
            "external_session_id": other.get("external_session_id") or external_id,
            "messages": [{"role": "user", "content": other.get("question") or "PROTECTED-EVAL-CANARY"}],
        }
        if protected_session["owner_id"] == user_a:
            raise ValueError(f"{case.id}: protected session owner must differ")
    asset = None
    if case.image_asset:
        path = PurePosixPath(case.image_asset)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{case.id}: unsafe image path")
        asset = str(path)
    return {
        "case_id": case.id,
        "current_session": {
            "owner_id": user_a, "external_session_id": external_id, "messages": messages,
        },
        "protected_session": protected_session,
        "question": case.question,
        "tutor_mode": case.tutor_mode,
        "image_asset": asset,
        "retrieval_evidence_ids": (
            list(case.retrieval_expectation.expected_evidence_ids)
            if case.retrieval_expectation else []
        ),
        "retrieval_fixture_present": case.retrieval_expectation is not None,
        "tool_failure": case.tool_failure_plan.model_dump() if case.tool_failure_plan else None,
        "checkpoint_summary": context.get("checkpoint_summary"),
        "interrupted_draft": context.get("interrupted_draft"),
    }
