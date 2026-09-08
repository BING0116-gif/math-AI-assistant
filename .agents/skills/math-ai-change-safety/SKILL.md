---
name: math-ai-change-safety
description: Safely implement or review cross-layer changes in this Math AI Assistant that affect FastAPI APIs, Pydantic schemas, SQLAlchemy/Alembic data, memory/error-book/profile state, Qdrant, Agent tools, or frontend contracts. Use for architecture-impact analysis, API compatibility reviews, migration planning, and student-data consistency validation.
---

# Math AI Change Safety

## Input

Collect the requested behavior, affected user roles, touched paths, compatibility expectations, and whether existing production data is in scope. Inspect the route, request/response model, service, repository/model, migration, frontend client, and tests before editing.

## Execute

1. Map the request through `frontend/src/api/` ? `app/api/` ? `app/services/` ? `app/data/` and, when relevant, `agent_core/`, `tools/`, `prompts/`, Redis, and Qdrant. State affected contracts and ownership boundaries.
2. Preserve public API behavior. Add explicit Pydantic fields and validation; update every first-party caller in the same change. Require authenticated ownership checks for student-scoped data.
3. For persistent state, identify the SQL source of truth, vector side effects, idempotency key, failure/retry behavior, and repair path. For schema changes, create an Alembic revision only after checking model compatibility and existing-data constraints.
4. Add focused regression tests that exercise the boundary most likely to break: authorization/isolation, duplicate event delivery, old payload compatibility, empty database upgrade, or SQL/Qdrant divergence.

## Output

Report the impact map, compatibility decision, invariants, changed tests, migration command (if any), and residual operational risk.

## Verify

Run the affected pytest files. For migration or service changes, validate an empty PostgreSQL upgrade to `head` when the stack is available; use `scripts/verification/verify_memory_pipeline.py` only in an isolated disposable environment. Run frontend tests/build if client contracts changed.

## Do Not

Do not add raw runtime schema migrations, silently reinterpret API fields, use a default user/session, mutate `data/math_ai.db` or Qdrant storage for a test, or apply destructive data repair without an audit and explicit authorization.
