"""Deterministic report builder shared by assessment and exam sessions."""
from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from typing import Any


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_session_report(session, *, planning_source: str | None = None) -> dict[str, Any]:
    question_by_id = {row.id: row for row in session.questions}
    attempts = sorted(session.attempts, key=lambda item: question_by_id[item.session_question_id].position)
    total = len(session.questions)
    unit_score = 100.0 / total if total else 0.0
    items: list[dict[str, Any]] = []
    by_code = defaultdict(lambda: {"total": 0, "correct": 0, "score": 0.0, "max_score": 0.0})
    errors: dict[str, int] = defaultdict(int)
    correct = 0
    for attempt in attempts:
        row = question_by_id[attempt.session_question_id]
        snapshot = dict(attempt.grading_snapshot or {})
        is_correct = bool(snapshot.get("correct"))
        correct += int(is_correct)
        snapshot.update({
            "position": row.position,
            "content": snapshot.get("question_content") or (row.snapshot or {}).get("content") or "",
            "question_type": (row.snapshot or {}).get("question_type"),
            "options": (row.snapshot or {}).get("options") or [],
            "score_awarded": round(unit_score if is_correct else 0.0, 2),
            "max_score": round(unit_score, 2),
        })
        items.append(snapshot)
        for code in snapshot.get("knowledge_point_codes") or []:
            bucket = by_code[code]
            bucket["total"] += 1
            bucket["correct"] += int(is_correct)
            bucket["score"] += unit_score if is_correct else 0.0
            bucket["max_score"] += unit_score
        if not is_correct:
            errors[snapshot.get("error_category") or "UNKNOWN"] += 1
    started, completed = _aware(session.started_at), _aware(session.completed_at)
    elapsed = max(0, int((completed - started).total_seconds())) if started and completed else None
    weakest = sorted(by_code, key=lambda code: (by_code[code]["correct"] / by_code[code]["total"], code))[:3]
    knowledge = [{
        "knowledge_point_code": code,
        **value,
        "score": round(value["score"], 1),
        "max_score": round(value["max_score"], 1),
        "accuracy": round(value["correct"] / value["total"], 3),
    } for code, value in sorted(by_code.items())]
    result = {
        "session_id": session.id, "mode": session.mode, "status": session.status,
        "completion_reason": session.completion_reason,
        "score": round((correct / total * 100) if total else 0.0, 1), "max_score": 100.0,
        "accuracy": round(correct / total, 3) if total else 0.0,
        "total": total, "correct": correct, "duration_seconds": elapsed,
        "results": items, "questions": items, "knowledge_breakdown": knowledge,
        "error_breakdown": [{"category": code, "count": count} for code, count in sorted(errors.items())],
        "next_practice_config": {"course_id": session.course_id, "version_id": session.version_id, "knowledge_point_codes": weakest, "question_count": min(10, max(5, total))} if weakest else None,
    }
    if planning_source is not None: result["planning_source"] = planning_source
    return result
