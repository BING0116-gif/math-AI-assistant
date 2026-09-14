# T15 Local Template Tracer

This tracer is a local development harness, not a production service. It accepts a versioned
`MathAnimationSpec`, resolves an enum-like `template_id` through a closed registry, verifies the
reviewed source hash, and invokes the pinned renderer image with fixed isolation arguments.

It never accepts Python source, source paths, scene names, Docker arguments, output paths, or
renderer image names from the spec. The three current templates accept no parameters.

## Run

From the repository root:

```powershell
python -m ops.math_animator_poc.tracer.cli `
  ops/math_animator_poc/tracer/examples/secant.json `
  --output-root artifacts/t15-phase1/tracer-cache
```

The first run renders into a SHA-256 cache directory. The same spec, renderer digest and reviewed
source hash produce the same cache key; a later run validates the MP4 hash before reporting a hit.

To exercise the observable T08 adapter pipeline:

```powershell
python -m ops.math_animator_poc.tracer.pipeline_cli `
  ops/math_animator_poc/tracer/examples/t08-tangent.json `
  --template-id secant_to_tangent `
  --output-root artifacts/t15-phase1/observable-pipeline
```

Each invocation writes an append-only JSONL event timeline under `events/`. The adapter calls the
existing T08 `MathVisualizer` first and only maps exact, MathVerifier-backed semantics. It currently
supports the fixed tangent and Riemann templates. Taylor mapping is deliberately rejected because
T08 does not yet expose a verified Taylor-polynomial sequence contract.

## Local durable queue

Submit and process a job in separate processes:

```powershell
python -m ops.math_animator_poc.tracer.local_queue_cli `
  --root artifacts/t15-phase1/local-queue `
  submit ops/math_animator_poc/tracer/examples/t08-tangent.json `
  --template-id secant_to_tangent `
  --idempotency-key local-demo-1

python -m ops.math_animator_poc.tracer.local_queue_cli `
  --root artifacts/t15-phase1/local-queue `
  work-once --worker-id local-worker-1
```

The file-backed prototype provides idempotent submit, short-lease claim, heartbeat, expired-lease
recovery, cooperative cancel and request hash verification. It writes only under the explicit
artifact root. It is for one trusted developer machine, is not FIFO-guaranteed, and has no user
ownership model; do not expose it through FastAPI or reuse it as the production task store.

## Local capability admission

The local `MathAnimationCapability` gate sits before queue submission:

```powershell
python -m ops.math_animator_poc.tracer.capability_cli `
  ops/math_animator_poc/tracer/examples/t08-tangent.json `
  --root artifacts/t15-phase1/capability `
  --template-id secant_to_tangent `
  --trigger user_explicit `
  --idempotency-key explicit-demo-1
```

`user_explicit` admits only after the T08 semantic check. `teaching_strategy` additionally requires
a finite `dynamic_process_score` of at least `0.8`. `none`, a lower score, an incompatible visual,
or the currently unsupported Taylor contract returns `t08_static` without creating a job.

This trigger is structured local input, not an LLM call. The capability does not import or invoke
DeepSeek, Qwen, or any other model provider and is not registered in the production orchestrator.

## Contract

```json
{
  "schema_version": 1,
  "template_id": "secant_to_tangent",
  "parameters": {}
}
```

Allowed template ids are `secant_to_tangent`, `riemann_sum`, and `taylor_approximation`.
Unknown/missing fields, unknown templates, non-finite JSON values and template parameters outside
the registry are rejected before Docker starts.

## Failure behavior

The renderer is limited both by a host subprocess timeout and `/usr/bin/timeout` inside the
container. A failure is retried once. A second failure writes `job.json` with
`fallback: "t08_static"` and exits unsuccessfully; it never generates or repairs Python code.

## Scope

- local CLI only;
- fixed, hash-pinned trusted scenes only;
- no FastAPI, database, Redis, Qdrant, frontend, Docker socket or student data;
- no authorization for server deployment or arbitrary Python execution.
