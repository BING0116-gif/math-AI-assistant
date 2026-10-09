"""Deterministic, auditable micro-diagnostics after an incorrect practice answer."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.data.database import get_db_session
from app.data.models import PracticeDiagnosticEvent, PracticeSession
from app.services.practice_service import PracticeError


def _prompt(snapshot: dict[str, Any], step: int = 0) -> tuple[str, dict[str, Any]]:
    content = str(snapshot.get("content") or "")
    if re.search(r"sin\s*x|sin\\", content, re.I) and ("lim" in content.lower() or "极限" in content):
        return "limit_equivalent_sin", {
            "title": "先不看答案，我们只判断下一步",
            "question": "当 x→0 时，sin x 与哪个式子等价？",
            "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "x²"}, {"id": "C", "text": "1/x"}],
            "correct_option": "A",
            "explanation": "先识别等价无穷小，再回到原式化简。",
        }
    if "ln" in content and ("导数" in content or "'" in content):
        return "derivative_product_rule", {
            "title": "先确认所用法则",
            "question": "两个函数相乘时，应使用哪个求导法则？",
            "options": [{"id": "A", "text": "乘积求导法则"}, {"id": "B", "text": "只分别求导后相乘"}, {"id": "C", "text": "常数求导法则"}],
            "correct_option": "A",
            "explanation": "识别函数结构后，再选择对应法则。",
        }
    mistakes = snapshot.get("common_mistakes") or {}
    items = mistakes.get("items") if isinstance(mistakes, dict) else []
    suggestion = str((items or [{}])[0].get("suggestion") or "先识别题目考查的知识点，再选择对应公式。")
    return "generic_strategy_check", {
        "title": "先确定解题方向",
        "question": "遇到这类题，下一步更合适的做法是？",
        "options": [{"id": "A", "text": suggestion}, {"id": "B", "text": "直接猜测最终答案"}, {"id": "C", "text": "忽略题目条件"}],
        "correct_option": "A",
        "explanation": suggestion,
    }


def _event_payload(event: PracticeDiagnosticEvent) -> dict[str, Any]:
    prompt = dict(event.prompt_snapshot or {})
    prompt.pop("correct_option", None)
    return {
        "event_id": event.id,
        "question_id": event.question_id,
        "step_index": event.step_index,
        "template_code": event.template_code,
        "prompt": prompt,
        "selected_answer": event.selected_answer,
        "correct": event.correct,
        "completed": event.correct is not None,
    }


async def _owned_context(db, user_id: str, session_id: str, question_id: str):
    session = (await db.execute(
        select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
            PracticeSession.mode == "practice",
        ).options(selectinload(PracticeSession.questions), selectinload(PracticeSession.attempts))
    )).scalar_one_or_none()
    if not session:
        raise PracticeError("SESSION_NOT_FOUND", "练习会话不存在")
    row = next((item for item in session.questions if item.question_id == question_id), None)
    attempt = next((item for item in session.attempts if item.question_id == question_id), None)
    if not row or not attempt:
        raise PracticeError("ATTEMPT_NOT_FOUND", "请先提交本题答案")
    if attempt.correct:
        raise PracticeError("DIAGNOSTIC_NOT_REQUIRED", "本题已答对，无需诊断")
    return session, row, attempt


async def start_diagnostic(user_id: str, session_id: str, question_id: str, idempotency_key: str) -> dict[str, Any]:
    async with get_db_session() as db:
        _, row, attempt = await _owned_context(db, user_id, session_id, question_id)
        existing = (await db.execute(select(PracticeDiagnosticEvent).where(PracticeDiagnosticEvent.attempt_id == attempt.id, PracticeDiagnosticEvent.step_index == 0))).scalar_one_or_none()
        if existing:
            return _event_payload(existing)
        code, prompt = _prompt(row.snapshot or {})
        event = PracticeDiagnosticEvent(user_id=user_id, session_id=session_id, question_id=question_id, attempt_id=attempt.id, template_code=code, step_index=0, prompt_snapshot=prompt, idempotency_key=idempotency_key)
        db.add(event); await db.flush()
        return _event_payload(event)


async def answer_diagnostic(user_id: str, session_id: str, question_id: str, answer: Any, idempotency_key: str) -> dict[str, Any]:
    async with get_db_session() as db:
        _, _, attempt = await _owned_context(db, user_id, session_id, question_id)
        event = (await db.execute(select(PracticeDiagnosticEvent).where(PracticeDiagnosticEvent.attempt_id == attempt.id, PracticeDiagnosticEvent.step_index == 0).with_for_update())).scalar_one_or_none()
        if not event:
            raise PracticeError("DIAGNOSTIC_NOT_STARTED", "请先开始诊断")
        if event.selected_answer is not None:
            if event.selected_answer != answer:
                raise PracticeError("IDEMPOTENCY_CONFLICT", "诊断步骤已经回答")
            return _event_payload(event)
        event.selected_answer = answer
        event.correct = str(answer) == str((event.prompt_snapshot or {}).get("correct_option"))
        event.idempotency_key = idempotency_key
        grading = dict(attempt.grading_snapshot or {})
        signals = dict(grading.get("learning_signals") or {})
        signals.update({"diagnostic_used": True, "diagnostic_steps": 1, "diagnostic_success": bool(event.correct), "hint_used": True})
        grading["learning_signals"] = signals
        attempt.grading_snapshot = grading
        await db.flush()
        payload = _event_payload(event)
        payload["explanation"] = (event.prompt_snapshot or {}).get("explanation")
        return payload


async def get_diagnostic(user_id: str, session_id: str, question_id: str) -> dict[str, Any]:
    async with get_db_session() as db:
        _, _, attempt = await _owned_context(db, user_id, session_id, question_id)
        event = (await db.execute(select(PracticeDiagnosticEvent).where(PracticeDiagnosticEvent.attempt_id == attempt.id, PracticeDiagnosticEvent.step_index == 0))).scalar_one_or_none()
        return {"started": bool(event), "diagnostic": _event_payload(event) if event else None}
