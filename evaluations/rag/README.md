# Phase 4 RAG quality evaluation

`v1/gold.json` is the versioned retrieval contract. It covers normal, ambiguous,
noisy, out-of-scope, unpublished, retired, wrong-but-plausible, and vector-down
cases. Student memory or account identifiers must never appear in result metadata.

Run the deterministic scorer with:

```powershell
python -m scripts.rag_quality_eval `
  --gold evaluations/rag/v1/gold.json `
  --results evaluations/rag/v1/offline_fixture_results.json `
  --output artifacts/phase4/rag-offline
```

The checked-in result file is an **offline fixture** for scorer and policy-gate
regression only. It is not Qdrant or embedding quality evidence. A real run must
write the same result shape, record the embedding model and Qdrant mode, and set
`mode` to `live_qdrant`. Reports must keep offline and live results separate.

Each run result contains:

- `case_id`, ordered `retrieved_ids`, and end-to-end `latency_ms`;
- `degraded=true` when the case intentionally exercises SQL fallback;
- non-sensitive retrieval metadata only.

The scorer reports Recall@K, MRR, irrelevant recall rate, p50/p95 latency,
publication-policy violations, and degradation-contract violations.
