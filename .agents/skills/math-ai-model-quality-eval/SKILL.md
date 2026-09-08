---
name: math-ai-model-quality-eval
description: Evaluate a Math AI Assistant behavior involving Qwen-VL-style visual question understanding, Qwen-Max-style mathematical answers, classification, RAG retrieval, agent planning, tool calls, or learning recommendations. Use when changing prompts/models/tools/retrieval, investigating answer quality, or creating repeatable AI quality regression cases.
---

# Math AI Model Quality Eval

## Input

Obtain a representative, non-sensitive evaluation set or reproducible failing case. Define the user intent, supplied image/text, expected mathematical result, required explanation properties, permitted tools/sources, and expected learning-data side effects.

## Execute

1. Classify the failure boundary: visual extraction, normalization, retrieval, agent planning/tool invocation, mathematical reasoning, streaming/format rendering, or memory/profile recommendation.
2. Build a small case matrix that includes normal, ambiguous/noisy, malformed, and wrong-but-plausible inputs. Keep image-derived claims separate from mathematical claims and retrieval evidence.
3. Score each case for extraction fidelity, final-answer correctness, reasoning/verifiability, retrieved-context grounding, tool/plan correctness, Chinese math/LaTeX rendering, safety, and absence of cross-user memory leakage.
4. Prefer deterministic assertions for parsing, routing, metadata, tool calls, and answer structure. Use a human-reviewed golden answer for open-ended mathematical quality; do not claim model quality from one successful prompt.
5. Convert stable cases into focused pytest coverage near `test_vision_tool*`, `test_classifier.py`, `test_task_planner.py`, `test_rag_*`, or `test_v3_prompt_system.py`.

## Output

Produce a concise evaluation table with cases, evidence, pass/fail criteria, observed result, root-cause boundary, and follow-up test. Distinguish model nondeterminism from deterministic implementation regressions.

## Verify

Run targeted tests with model/network calls mocked unless an explicit integration evaluation is authorized. For live models, record model/config, timestamp, inputs, and cost/latency constraints; redact student data and secrets.

## Do Not

Do not treat a fluent answer as correct, change prompts and code in one unmeasured step, store real student images/conversations in fixtures, or promote a model output to a truth source without mathematical verification.
