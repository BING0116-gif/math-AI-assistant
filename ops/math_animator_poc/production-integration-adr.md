# ADR: Production integration boundary for MathAnimator

- Status: `PROPOSED — IMPLEMENTATION AND DEPLOYMENT BLOCKED`
- Date: 2026-09-14
- Scope: FastAPI contract, owner-bound persistence, worker/renderer boundary, media authorization
- Explicitly excluded: LLM-generated Python, model-provider APIs, immediate implementation or deployment

## Context

The local tracer proves strict T08 adaptation, fixed-template rendering, retries, fallback, caching,
observable events and lease-based task recovery. Production integration changes the trust boundary:
authenticated students create durable resources, multiple workers contend for jobs, and media must
never cross owners.

“Production API” in this ADR means the application's own FastAPI HTTP API. It does not mean the
DeepSeek, Qwen-VL or any other LLM API. The proposed v1 path performs no model-provider request.

Existing tables are not suitable:

- `ContentTask` has no `user_id` and represents admin content processing;
- `KnowledgePointResource` is versioned catalog content attached to a knowledge point;
- `SourceDocument` represents admin-ingested source files.

Reusing any of them would either lose ownership or silently change existing semantics. Production
MathAnimator therefore requires dedicated owner-bound records.

## Decision

Use three new SQL tables as the production source of truth:

1. `animation_jobs`: owner, validated request snapshot, state, lease/retry and result summary;
2. `animation_job_events`: append-only state evidence with unique event ids and monotonic sequence;
3. `animation_artifacts`: owner-bound metadata for validated MP4/thumbnail/GIF objects.

The web process validates and enqueues only. A dedicated animation worker claims SQL jobs and calls
an external one-shot runner. The renderer receives a validated fixed-template spec, has no database,
Redis, Qdrant or model credentials, and never receives a `user_id`.

```text
authenticated client
  -> FastAPI animation API
  -> AnimationService (owner + idempotency + T08 validation)
  -> PostgreSQL AnimationJob/Event
  -> dedicated worker claim/heartbeat
  -> external one-shot fixed-template renderer
  -> validated object under storage root
  -> AnimationArtifact metadata
  -> owner-scoped media response
```

## Public HTTP contract

All success bodies keep the existing envelope:

```json
{"code": 0, "data": {}, "message": "ok"}
```

### `POST /api/animations/jobs`

Authenticated student request. Public clients may only use an explicit user trigger:

```json
{
  "idempotency_key": "client-generated-8-to-128-chars",
  "template_id": "secant_to_tangent",
  "trigger": "user_explicit",
  "visual_spec": {"type": "tangent_line"}
}
```

Rules:

- obtain `user_id` exclusively from authenticated request state;
- never accept `user_id`, source paths, Python, scene names, image names or Docker arguments;
- public `trigger` is the literal `user_explicit`; a client-supplied teaching score is forbidden;
- run T08 `MathVisualizer`/MathVerifier and strict template compatibility before insert;
- body limit follows the T08 limit and must be enforced before expensive validation;
- return HTTP 202 with `job_id`, `status`, `template_id`, `created_at` and polling URL;
- same `(user_id, idempotency_key)` and same request fingerprint returns the existing job;
- same key with a different fingerprint returns HTTP 409 `IDEMPOTENCY_CONFLICT`.

An internal service method may use `teaching_strategy`, but the score is server-derived, audited and
not accepted by the public schema. It still cannot bypass T08 or template checks.

### `GET /api/animations/jobs/{job_id}`

Query with both `job_id` and authenticated `user_id`. A missing or other-owner id returns the same
404 `ANIMATION_JOB_NOT_FOUND`; do not reveal resource existence with different responses. Return:

- `pending | running | succeeded | fallback | failed | cancelled`;
- bounded progress/stage, attempt count and timestamps;
- media metadata only after success;
- deterministic fallback reason after `fallback`;
- sanitized error code/message, never raw stderr, host paths, environment or secrets.

### `POST /api/animations/jobs/{job_id}/cancel`

Owner-scoped and idempotent. Pending jobs become cancelled immediately. Running jobs set
`cancel_requested`; the worker asks the external runner to stop and suppresses artifact publication.
Terminal success/fallback/failed remains terminal; repeated cancellation returns current state.

### `GET /api/animations/jobs/{job_id}/artifacts/{kind}`

`kind` is an enum (`video`, `thumbnail`, later `gif`). Resolve by `(job_id, user_id, kind)` and return
404 for both missing and foreign resources. Requirements:

- resolve a relative logical `storage_key` under `ANIMATION_STORAGE_ROOT` with traversal checks;
- never serialize `storage_key` or an absolute path to the client;
- verify artifact status, size and SHA-256 before first publication;
- set fixed MIME from artifact kind, `X-Content-Type-Options: nosniff`, safe inline disposition and
  private cache controls;
- support bounded HTTP range requests for MP4 without reading the whole file into memory;
- do not serve partial renderer output or a job that was cancelled during rendering.

List endpoint is optional for v1. If added, it must be owner-scoped, cursor-paginated and bounded.

## SQL model proposal

### `AnimationJob`

Required fields:

- `id` UUID/string primary key;
- `user_id` non-null FK `users.id ON DELETE CASCADE`, indexed;
- `idempotency_key` varchar(128), `request_fingerprint` char(64);
- `schema_version`, `template_id`, `template_source_sha256`, `renderer_image_digest`;
- `trigger` (`user_explicit | teaching_strategy`) and server-side `admission_snapshot` JSON;
- validated `visual_spec_snapshot` JSON; do not store arbitrary code or secrets;
- `status`, `stage`, `attempt_count`, `max_attempts=2`, `recovery_count`;
- `worker_id`, `heartbeat_at`, `lease_expires_at`, `cancel_requested`;
- `cache_key`, `fallback_kind`, sanitized `error_code/error_message`;
- `created_at`, `updated_at`, `started_at`, `completed_at`.

Constraints and indexes:

- unique `(user_id, idempotency_key)`;
- check status, trigger, attempt bounds and SHA-256/digest lengths;
- claim index `(status, lease_expires_at, created_at)`;
- owner list index `(user_id, created_at)`;
- optimistic state updates include expected status and worker id.

### `AnimationJobEvent`

- `id` UUID and globally unique `event_id`;
- `job_id` FK cascade, `sequence` positive integer;
- `event_type`, `stage`, `status`, bounded/sanitized `details` JSON, `created_at`;
- unique `(job_id, sequence)` and `(event_id)`.

The transition and its event must commit in one transaction. Replayed worker messages use the same
`event_id`, so event delivery cannot advance the state twice.

### `AnimationArtifact`

- `id`, `job_id` FK cascade and non-null `user_id` FK cascade;
- enum `kind`, relative `storage_key`, fixed MIME, SHA-256, byte size;
- width, height, frame count/duration where applicable;
- `validation_status`, `created_at` and `published_at`;
- unique `(job_id, kind)` and owner lookup index `(user_id, job_id, kind)`.

Keeping `user_id` on the artifact intentionally makes direct owner-scoped lookup possible. Service
creation must copy it from the locked job row; clients never provide it.

## State machine and idempotency

```text
pending -> running -> succeeded
                   -> fallback
                   -> failed
                   -> cancelled
running --expired lease--> running (new worker, recovery_count + 1)
pending -----------------> cancelled
```

- renderer attempt count is at most two; lease recovery does not reset attempts;
- a worker may finish only a row it owns in `running` state;
- completion uses a conditional update and inserts a unique event in one transaction;
- cancellation wins over late render success: the artifact may remain in quarantine/cache but is not
  linked or published for the cancelled job;
- request fingerprint includes canonical validated visual spec, template id, trigger policy version,
  template source hash and renderer digest;
- cache is owner-scoped by default. Cross-user reuse is allowed only for audited standard templates
  whose canonical input contains no user/question text, and still creates owner-bound artifact rows.

## Storage and runner boundary

- add a dedicated `ANIMATION_STORAGE_ROOT`; do not reuse content-ingestion folders;
- write renderer output to a quarantine key, validate, then atomically publish to a final logical key;
- web and ordinary workers never mount `/var/run/docker.sock`;
- a dedicated runner controller starts one-shot containers/jobs through a constrained interface;
- renderer image is pinned by digest and receives one read-only trusted scene plus one output mount;
- no network, non-root, read-only root, drop all capabilities, no-new-privileges, seccomp/AppArmor,
  CPU/memory/PID/time/output limits;
- renderer response contains only exit category and artifact manifest; raw stderr stays bounded in
  restricted operational logs and never enters student responses.

## Configuration proposal

All values come from environment-backed settings, with production-safe defaults:

- `MATH_ANIMATION_ENABLED=false`;
- `ANIMATION_STORAGE_ROOT=./runtime/animations`;
- `ANIMATION_RENDERER_IMAGE=<approved digest>`;
- `ANIMATION_RENDER_TIMEOUT_SECONDS=30`;
- `ANIMATION_MAX_OUTPUT_BYTES=20971520`;
- `ANIMATION_MAX_ATTEMPTS=2`;
- `ANIMATION_WORKER_CONCURRENCY=1`;
- `ANIMATION_JOB_LEASE_SECONDS=60`.

The feature flag remains false through migration and dark launch. No model API key is added.

## Migration plan

Create one Alembic revision from the verified current head `c9d0e1f2a3b4` after the implementation
gate is approved. It creates the three tables, constraints and indexes without touching existing
rows. Verification must include:

1. empty PostgreSQL `upgrade head`;
2. upgrade from the current production-compatible head;
3. model/metadata agreement;
4. insert/ownership/idempotency/claim constraint tests;
5. downgrade only in a disposable database.

Production rollback disables the feature flag and drains/stops animation workers first. Database
tables and artifacts are retained for audit and recovery; do not automatically downgrade or delete
student media. A later audited cleanup may remove expired artifacts.

## Rejected alternatives

- reuse `ContentTask`: rejected because it has no student owner and different business semantics;
- reuse `KnowledgePointResource`: rejected because it is shared catalog content;
- store binaries in PostgreSQL: rejected due size/streaming/backup cost;
- expose local file queue through FastAPI: rejected; it lacks multi-user transactional ownership;
- let clients submit teaching scores: rejected as a quota/admission bypass;
- render in FastAPI or mount Docker socket: rejected as host-compromise boundary;
- execute LLM/user Python: rejected and outside the approved risk waiver.

## Implementation status (2026-09-14)

The disabled-by-default implementation now includes owner-scoped create/status/cancel/media APIs,
the transactional SQL worker state machine, a standalone worker entrypoint, a fixed-template
one-shot Docker controller, quarantine validation/atomic publication, bounded MP4 range responses,
and an Agent tool surfaced inside the existing conversation UI. MathAnimator is not a standalone
student module: `math_animate` uses trusted request context for owner identity, applies a deterministic
teaching-value guard around model tool selection, enqueues the fixed template, and emits an
`animation_job` SSE event after the accompanying text explanation. The chat message persists only the
public job projection and restores its inline animation card when the conversation is reopened.
Run the controller separately with:

```text
python -m app.tasks.animation_worker
```

The controller host needs Docker CLI access, PostgreSQL connectivity and the shared animation
storage root. The FastAPI web process must not receive Docker socket access. The flag remains false;
this implementation status is not deployment approval.

## Approval gates

Implementation remains blocked until the owner explicitly approves this production data/API design.
Deployment remains separately blocked until real-user validation, a fresh image scan/risk review,
empty-PostgreSQL migration evidence, authorization tests, media-path tests and isolated runner escape
tests all pass.
