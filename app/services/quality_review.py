"""Owner-safe quality review queue operations for AI interaction runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select

from app.data.database import get_db_session
from app.data.models import AIInteractionRun
from app.observability import AGENT_REVIEW_VERDICTS
from app.security.audit import get_audit_logger


_VERDICTS = {"pass", "fail"}


def _safe_issues(issues: Any) -> list[dict[str, str]]:
    """Expose issue codes/locations only; never return free-text answer fragments."""
    if not isinstance(issues, list):
        return []
    safe: list[dict[str, str]] = []
    for item in issues[:20]:
        if isinstance(item, dict) and item.get("code"):
            row = {"code": str(item["code"])[:80]}
            if item.get("location"):
                row["location"] = str(item["location"])[:120]
            safe.append(row)
    return safe


async def list_review_queue(*, status: str = "pending", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    status = status if status in {"pending", "graded", "all"} else "pending"
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    async with get_db_session() as db:
        base = select(AIInteractionRun).where(AIInteractionRun.quality_sampled.is_(True))
        if status == "pending":
            base = base.where(AIInteractionRun.review_verdict.is_(None))
        elif status == "graded":
            base = base.where(AIInteractionRun.review_verdict.is_not(None))
        priority = case((AIInteractionRun.critic_verdict == "fail", 0), (AIInteractionRun.critic_verdict == "warn", 1), else_=2)
        rows = (await db.execute(base.order_by(priority, AIInteractionRun.created_at.asc()).offset(offset).limit(limit))).scalars().all()
        total_query = select(func.count()).select_from(base.subquery())
        total = int(await db.scalar(total_query) or 0)
    return {
        "items": [
            {
                "run_id": row.id,
                "request_kind": row.request_kind,
                "tutor_mode": row.tutor_mode,
                "critic_verdict": row.critic_verdict,
                "critic_issues": _safe_issues(row.critic_issues),
                "review_verdict": row.review_verdict,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "status": status,
    }


async def submit_review(*, run_id: str, reviewer_id: str, verdict: str, issue_codes: list[str]) -> dict[str, Any]:
    if verdict not in _VERDICTS:
        raise ValueError("review verdict must be pass or fail")
    clean_codes = sorted({str(code).strip()[:80] for code in issue_codes if str(code).strip()})[:20]
    async with get_db_session() as db:
        run = await db.get(AIInteractionRun, run_id)
        if run is None or not run.quality_sampled:
            raise LookupError("review run not found")
        old = run.review_verdict
        run.review_verdict = verdict
        run.reviewer_id = reviewer_id
        run.critic_issues = [{"code": code} for code in clean_codes] or run.critic_issues
    if old != verdict:
        AGENT_REVIEW_VERDICTS.labels(verdict=verdict, reviewer_type="admin").inc()
        get_audit_logger().log_modification(
            reviewer_id,
            "ai_quality_review",
            run_id,
            {"review_verdict": old},
            {"review_verdict": verdict, "issue_codes": clean_codes},
            ["review_verdict", "reviewer_id", "critic_issues"],
        )
    return {"run_id": run_id, "review_verdict": verdict, "issue_codes": clean_codes}
