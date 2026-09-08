"""Safety guards for live evaluations and database side-effect audits."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class EvaluationSafetyError(RuntimeError):
    pass


def redact_database_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    username = f"{parsed.username}@" if parsed.username else ""
    return urlunsplit((parsed.scheme, f"{username}{hostname}{port}", parsed.path, "", ""))


def validate_eval_database_url(eval_url: str | None, application_url: str | None = None) -> str:
    if not eval_url:
        raise EvaluationSafetyError("EVAL_DATABASE_URL is required for live evaluation")
    parsed = urlsplit(eval_url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        raise EvaluationSafetyError("live evaluation requires PostgreSQL")
    database_name = parsed.path.lstrip("/").lower()
    if not database_name or not ("_eval" in database_name or "_test" in database_name):
        raise EvaluationSafetyError("evaluation database name must contain _eval or _test")
    configured_application_url = application_url or os.environ.get("DATABASE_URL")
    if configured_application_url and _database_target(configured_application_url) == _database_target(eval_url):
        raise EvaluationSafetyError("EVAL_DATABASE_URL must not equal the application DATABASE_URL")
    return eval_url


def _normalise_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1).rstrip("/")


def _database_target(url: str) -> tuple[str, int, str]:
    parsed = urlsplit(_normalise_url(url))
    return (parsed.hostname or "", parsed.port or 5432, parsed.path.rstrip("/").lower())


AUDITED_TABLES = (
    "chat_sessions",
    "chat_messages",
    "ai_interaction_runs",
    "practice_attempts",
    "error_items",
    "user_knowledge_states",
    "review_schedules",
    "practice_sessions",
    "questions",
    "learning_records",
    "memories",
    "user_profiles",
    "event_idempotency",
)


def side_effect_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    """Return count deltas and flag in-place updates detected by table fingerprints."""
    delta: dict[str, int] = {}
    for table in AUDITED_TABLES:
        old, new = before.get(table, 0), after.get(table, 0)
        if isinstance(old, dict) and isinstance(new, dict):
            count_delta = int(new.get("count", 0)) - int(old.get("count", 0))
            delta[table] = count_delta if count_delta else (1 if old.get("digest") != new.get("digest") else 0)
        else:
            delta[table] = int(new) - int(old)
    return delta


def forbidden_side_effects(delta: dict[str, int], forbidden_tables: list[str]) -> list[str]:
    return [table for table in forbidden_tables if delta.get(table, 0) != 0]
