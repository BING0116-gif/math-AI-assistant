"""Owner-scoped mastery evidence and append-only correction reports."""
from __future__ import annotations
from sqlalchemy import select
from app.data.database import get_db_session
from app.data.models import MasteryCorrectionEvent, PracticeAttempt, UserKnowledgeState, KnowledgePoint

async def mastery_evidence(user_id: str, code: str) -> dict:
    async with get_db_session() as db:
        state = (await db.execute(select(UserKnowledgeState).where(UserKnowledgeState.user_id == user_id, UserKnowledgeState.knowledge_point_code == code))).scalar_one_or_none()
        attempts = list((await db.execute(select(PracticeAttempt).where(PracticeAttempt.user_id == user_id).order_by(PracticeAttempt.submitted_at.desc()).limit(100))).scalars())
        attempts = [a for a in attempts if code in ((a.grading_snapshot or {}).get("knowledge_point_codes") or [])][:30]
    return {
        "knowledge_point_code": code,
        "mastery": round(float(state.mastery), 4) if state else 0.0,
        "confidence": round(float(state.confidence), 4) if state else 0.0,
        "evidence_count": int(state.attempts_count) if state else 0,
        "calculation_version": state.calculation_version if state else "uks-rules-v1",
        "change_reason": state.calculation_reason if state else {},
        "evidence": [{
            "attempt_id": a.id, "question_id": a.question_id, "occurred_at": a.submitted_at,
            "correct": bool(a.correct), "error_type": (a.grading_snapshot or {}).get("error_category"),
            "question": (a.grading_snapshot or {}).get("question_content", "")[:500],
        } for a in attempts],
    }

async def report_correction(*, user_id: str, code: str, correction_type: str, proposed_value: str, reason: str, idempotency_key: str) -> dict:
    if correction_type not in {"error_type", "knowledge_point"}: raise ValueError("纠正类型非法")
    proposed_value = proposed_value.strip()
    if not proposed_value: raise ValueError("纠正内容不能为空")
    async with get_db_session() as db:
        prior = (await db.execute(select(MasteryCorrectionEvent).where(MasteryCorrectionEvent.user_id == user_id, MasteryCorrectionEvent.idempotency_key == idempotency_key))).scalar_one_or_none()
        if prior:
            if prior.knowledge_point_code != code or prior.proposed_value != proposed_value: raise ValueError("幂等键已用于其他纠正")
            return _out(prior)
        if correction_type == "knowledge_point":
            point = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.code == proposed_value, KnowledgePoint.status == "active"))).scalar_one_or_none()
            if point is None: raise ValueError("目标知识点不存在")
        evidence = await mastery_evidence(user_id, code)
        original = code if correction_type == "knowledge_point" else next((item.get("error_type") for item in evidence["evidence"] if item.get("error_type")), None)
        row = MasteryCorrectionEvent(user_id=user_id, knowledge_point_code=code, correction_type=correction_type, original_value=original, proposed_value=proposed_value, reason=reason.strip()[:1000], evidence_snapshot={"evidence_count": evidence["evidence_count"], "calculation_version": evidence["calculation_version"]}, idempotency_key=idempotency_key)
        db.add(row); await db.flush(); return _out(row)

def _out(row):
    created = row.created_at.isoformat() if row.created_at else None
    if created and "+" not in created and not created.endswith("Z"):
        created += "+00:00"
    return {"correction_id": row.id, "knowledge_point_code": row.knowledge_point_code, "correction_type": row.correction_type, "original_value": row.original_value, "proposed_value": row.proposed_value, "reason": row.reason, "created_at": created}
