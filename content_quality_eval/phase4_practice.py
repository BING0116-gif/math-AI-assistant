"""Machine checks and human-review coverage for the 195 authored questions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from app.services.calculus_phase5 import POINTS
from app.services.phase5_content import GOLDEN
from app.services.phase5_standard_content import DESCRIPTIONS, STANDARD
from app.services.phase5_standard_practice import PRACTICE


HIGH_RISK_CODE_MARKERS = (
    "theorem", "limit", "improper", "extrema", "monotonicity", "concavity",
    "l-hopital", "mean-value", "volume", "surface", "fluid", "work",
)


def _question_id(code_index: int, sequence: int) -> str:
    return f"P5S{code_index:02d}{sequence}"


def _normalized_bank() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    names = {code: name for code, name, *_ in POINTS}
    for code_index, (code, items) in enumerate(PRACTICE.items(), start=1):
        for sequence, (level, difficulty, prompt, options, answer, analysis) in enumerate(items, start=1):
            rows.append({
                "question_id": _question_id(code_index, sequence),
                "knowledge_code": code,
                "knowledge_name": names[code],
                "sequence": sequence,
                "level": level,
                "difficulty": difficulty,
                "prompt": prompt,
                "options": [{"id": key, "text": text} for key, text in options],
                "answer": answer,
                "analysis": analysis,
            })
    return rows


def required_human_review_ids(rows: list[dict[str, Any]]) -> set[str]:
    required: set[str] = set()
    for row in rows:
        if row["sequence"] == 1:
            required.add(row["question_id"])
        if row["sequence"] in {2, 3}:
            required.add(row["question_id"])
        if any(marker in row["knowledge_code"] for marker in HIGH_RISK_CODE_MARKERS):
            required.add(row["question_id"])
    return required


def audit_phase4_practice(reviews: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _normalized_bank()
    failures: list[str] = []
    all_point_codes = {code for code, *_ in POINTS} - set(GOLDEN)
    if set(PRACTICE) != all_point_codes:
        failures.append("knowledge_point_coverage_mismatch")
    if len(PRACTICE) != 39 or len(rows) != 195:
        failures.append(f"unexpected_bank_shape:{len(PRACTICE)}:{len(rows)}")

    expected_shape = [("基础", 2), ("基础", 2), ("常规", 3), ("常规", 3), ("进阶", 4)]
    prompts = Counter(row["prompt"].strip() for row in rows)
    for code, items in PRACTICE.items():
        shape = [(item[0], item[1]) for item in items]
        if shape != expected_shape:
            failures.append(f"{code}:invalid_level_shape")
        if code not in STANDARD or code not in DESCRIPTIONS:
            failures.append(f"{code}:missing_lesson_source")

    for row in rows:
        qid = row["question_id"]
        option_ids = [item["id"] for item in row["options"]]
        option_texts = [item["text"].strip() for item in row["options"]]
        if not row["prompt"].strip() or not row["analysis"].strip():
            failures.append(f"{qid}:blank_prompt_or_analysis")
        if option_ids != ["A", "B", "C", "D"]:
            failures.append(f"{qid}:invalid_option_ids")
        if len(set(option_texts)) != 4 or any(not text for text in option_texts):
            failures.append(f"{qid}:duplicate_or_blank_option")
        if row["answer"] not in option_ids:
            failures.append(f"{qid}:invalid_answer_reference")
        elif dict((item["id"], item["text"].strip()) for item in row["options"])[row["answer"]] != row["analysis"].strip():
            failures.append(f"{qid}:answer_analysis_mismatch")
        if row["knowledge_name"] not in row["prompt"]:
            failures.append(f"{qid}:knowledge_point_prompt_mismatch")
    failures.extend(
        f"duplicate_prompt:{prompt}" for prompt, count in prompts.items() if count > 1
    )

    required_reviews = required_human_review_ids(rows)
    review_rows = (reviews or {}).get("questions", {})
    reviewer = str((reviews or {}).get("reviewer", "")).strip()
    reviewed_ids = {
        qid for qid, review in review_rows.items()
        if isinstance(review, dict)
        and review.get("decision") == "approved"
        and str(review.get("note", "")).strip()
    }
    review_failures: list[str] = []
    if reviews is not None:
        if len(reviewer) < 3:
            review_failures.append("accountable_reviewer_required")
        missing_reviews = sorted(required_reviews - reviewed_ids)
        if missing_reviews:
            review_failures.append(f"missing_required_reviews:{len(missing_reviews)}")
    else:
        missing_reviews = sorted(required_reviews)

    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    machine_passed = not failures
    human_review_complete = reviews is not None and not review_failures
    return {
        "schema_version": "1.0",
        "bank_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "point_count": len(PRACTICE),
        "question_count": len(rows),
        "level_counts": dict(Counter(row["level"] for row in rows)),
        "difficulty_counts": dict(Counter(str(row["difficulty"]) for row in rows)),
        "machine_checks": {
            "passed": machine_passed,
            "failures": failures,
        },
        "human_review": {
            "status": "complete" if human_review_complete else "pending",
            "reviewer": reviewer or None,
            "required_count": len(required_reviews),
            "approved_count": len(required_reviews.intersection(reviewed_ids)),
            "missing_ids": missing_reviews,
            "failures": review_failures,
        },
        "status": "approved" if machine_passed and human_review_complete else (
            "machine_passed_human_pending" if machine_passed else "failed"
        ),
        "questions": rows,
    }
