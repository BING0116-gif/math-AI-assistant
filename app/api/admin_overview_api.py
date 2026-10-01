"""管理员后台汇总概览 API。

该接口只返回聚合计数，不返回聊天正文、学生画像、错题详情或用户标识。
"""

from fastapi import APIRouter, Request
from sqlalchemy import func, or_, select

from app.data.database import get_db_session
from app.data.models import (
    ImportBatch,
    LearningRecord,
    Question,
    User,
)
from app.security.access_control import require_admin_role

router = APIRouter(prefix="/api/admin", tags=["管理员概览"])


async def _count_by_status(model, column) -> dict[str, int]:
    async with get_db_session() as session:
        rows = (
            await session.execute(
                select(column, func.count()).select_from(model).group_by(column)
            )
        ).all()
    return {str(status or "unknown"): int(count) for status, count in rows}


@router.get("/overview")
async def get_overview(request: Request):
    require_admin_role(request)

    async with get_db_session() as session:
        total_users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        active_users = int(
            await session.scalar(
                select(func.count()).select_from(User).where(User.is_active.is_(True))
            )
            or 0
        )
        admin_users = int(
            await session.scalar(
                select(func.count()).select_from(User).where(User.role == "admin")
            )
            or 0
        )
        student_users = int(
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(or_(User.role != "admin", User.role.is_(None)))
            )
            or 0
        )
        learning_events = int(
            await session.scalar(select(func.count()).select_from(LearningRecord)) or 0
        )
        active_learners = int(
            await session.scalar(
                select(func.count(func.distinct(LearningRecord.user_id))).select_from(
                    LearningRecord
                )
            )
            or 0
        )

    question_status = await _count_by_status(Question, Question.review_status)
    import_status = await _count_by_status(ImportBatch, ImportBatch.status)

    return {
        "code": 0,
        "data": {
            "users": {
                "total": total_users,
                "active": active_users,
                "students": student_users,
                "admins": admin_users,
            },
            "question_bank": {
                "draft": question_status.get("draft", 0),
                "reviewed": question_status.get("reviewed", 0),
                "published": question_status.get("published", 0),
                "retired": question_status.get("retired", 0),
            },
            "imports": import_status,
            "learning": {
                "active_learners": active_learners,
                "learning_events": learning_events,
            },
        },
    }
