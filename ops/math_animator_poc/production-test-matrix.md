# MathAnimator production implementation test matrix

This matrix is executable guidance for the future implementation. It does not authorize production
code or deployment.

## API and ownership

| Case | Expected assertion |
|---|---|
| unauthenticated create/status/cancel/media | 401 before service execution |
| user A creates and reads own job | 202 create, 200 status, standard response envelope |
| user B reads/cancels user A job | identical 404 response; no existence leak |
| user B requests user A artifact | 404; storage resolver not called |
| client includes `user_id` | schema rejects unknown field |
| client includes teaching score or `teaching_strategy` trigger | schema rejects; public trigger is user-explicit only |
| unknown template/Python/path/scene/image argument | 422 before task insert or runner call |
| status error payload | no stderr, absolute path, environment, token or internal key |

## Idempotency and state

| Case | Expected assertion |
|---|---|
| same owner/key/same canonical request | same job id; one row and one initial event |
| same owner/key/different request | 409 `IDEMPOTENCY_CONFLICT` |
| different owners/same key | distinct owner-scoped jobs |
| two workers claim concurrently | exactly one owns each job; no duplicate render |
| wrong worker heartbeat/finish | conditional update affects zero rows |
| expired lease | one recovery claim, preserved attempt count, recovery count increments |
| duplicate completion event id | one transition/event only |
| first render failure | one retry; attempt count becomes two |
| second render failure | terminal fallback/failed according to policy; no third call |
| cancel pending | cancelled immediately; renderer never called |
| cancel running then late success | cancelled wins; artifact not published |

## T08 and admission

| Case | Expected assertion |
|---|---|
| verified tangent `y=x²` at `x=1` | fixed secant template admitted |
| altered slope/point/expression | MathVerifier/adapter rejects |
| verified `x²` integral on `[0,2]` | fixed Riemann template admitted |
| partial/clipped T08 visual | animation rejected; T08 static preserved |
| Taylor before verified sequence contract | deterministic static fallback |
| internal teaching score below threshold | no job created |
| public client sends high score | request schema rejects field |

## Media and storage

| Case | Expected assertion |
|---|---|
| storage key contains `..`, drive prefix, UNC or absolute path | rejected before filesystem access |
| symlink escapes storage root | rejected after resolved-path containment check |
| wrong MIME/extension, missing `ftyp`, oversize or hash mismatch | quarantine; never published |
| valid MP4 full request | owner-scoped stream, fixed MIME and security headers |
| valid bounded range request | correct 206/content-range without full-file load |
| malformed or excessive range | 416 |
| cancelled/failed/partial artifact | 404, never streamed |
| cache hit from another owner | new owner-bound artifact row; no source-owner metadata leak |

## Migration and operations

| Case | Expected assertion |
|---|---|
| empty PostgreSQL upgrade to head | succeeds with all constraints/indexes |
| upgrade from `c9d0e1f2a3b4` | existing row counts unchanged |
| SQLAlchemy metadata vs migration | no unexpected diff |
| feature flag false | routes return controlled unavailable response; no worker starts |
| renderer unavailable | bounded failure/fallback; chat response remains usable |
| web restart with queued/running jobs | SQL job remains; expired lease is recoverable |
| worker restart | no attempt reset or duplicate artifact publication |
| image digest mismatch or scan gate failure | readiness blocker; runner refuses job |

## Suggested test files

- `tests/test_animation_api.py`: schema, envelope, authentication, ownership and media access;
- `tests/test_animation_service.py`: idempotency, transitions, cancellation and cache scope;
- `tests/test_animation_worker.py`: claim, heartbeat, lease recovery, retry and renderer boundary;
- `tests/test_animation_storage.py`: path containment, validation, range responses and quarantine;
- `tests/test_animation_migration.py`: constraints, indexes and upgrade evidence;
- extend `tests/test_permissions_and_deletion.py`: user deletion and artifact/job ownership cleanup;
- extend `tests/test_math_visualizer.py`: any new verified Taylor sequence contract.
