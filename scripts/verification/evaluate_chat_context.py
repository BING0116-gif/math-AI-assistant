"""Run synthetic, non-student summary fidelity cases against the configured model.

Usage: python scripts/verification/evaluate_chat_context.py [fixture.json]
This calls the configured model. It prints only synthetic case IDs and scores.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from app.services.chat_context_checkpoint import _validate_summary, summarize_source


async def main(path: Path) -> int:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if len(sys.argv) > 2:
        cases = [case for case in cases if case["id"] == sys.argv[2]]
    failures = 0
    for case in cases:
        source = [{"id": index, "role": "user", "content": content}
                  for index, content in enumerate(case["messages"], start=1)]
        try:
            response = await summarize_source(source)
            if response.partial:
                raise ValueError("truncated response")
            summary = _validate_summary(response.parsed_json, {item["id"] for item in source})
            rendered = json.dumps(summary, ensure_ascii=False)
            if os.getenv("CONTEXT_EVAL_SHOW_SYNTHETIC") == "1":
                print(json.dumps({"case": case["id"], "synthetic_summary": summary}, ensure_ascii=False))
            preserved = {phrase: phrase in rendered for phrase in case["must_preserve"]}
            any_terms = case.get("must_contain_any", [])
            any_found = not any_terms or any(phrase in rendered for phrase in any_terms)
            structure_ok = (not case.get("must_have_open_question") or bool(summary["open_questions"])) and (
                not case.get("confirmed_facts_empty") or not summary["confirmed_facts"])
            forbidden = {phrase: phrase in rendered for phrase in case["must_not_assert"]}
            passed = all(preserved.values()) and any_found and structure_ok and not any(forbidden.values())
            print(json.dumps({"case": case["id"], "passed": passed, "preserved": preserved,
                "any_required_found": any_found, "structure_ok": structure_ok,
                "forbidden_present": forbidden, "model": response.model,
                "prompt_tokens": response.usage.get("prompt_tokens"),
                "completion_tokens": response.usage.get("completion_tokens"),
                "latency_ms": round(response.latency_ms)}, ensure_ascii=False))
            failures += not passed
        except Exception as exc:
            failures += 1
            print(json.dumps({"case": case["id"], "passed": False, "error": str(exc)[:200],
                "finish_reason": getattr(locals().get("response"), "finish_reason", None),
                "response_preview": getattr(locals().get("response"), "content", "")[:160]}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    fixture = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/context_compression_cases.json")
    raise SystemExit(asyncio.run(main(fixture)))
