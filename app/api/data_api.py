import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse

from app.data.database import get_db_session
from app.data.repositories import (
    LearningRecordRepository,
    UserRepository,
    ChatSessionRepository,
)
from app.services.cache import get_cache_manager
from app.security.audit import get_audit_logger
from app.security.access_control import verify_resource_ownership
from app.security.encryption import DataEncryption

router = APIRouter(prefix="/api/data", tags=["数据管理"])


@router.get("/export")
async def export_user_data(
    http_request: Request,
    export_format: str = Query("json", pattern="^(json|csv)$"),
):
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")

    try:
        async with get_db_session() as db:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(user_id)

            record_repo = LearningRecordRepository(db)
            records = await record_repo.get_recent_records(
                user_id, days=365, limit=10000
            )

            session_repo = ChatSessionRepository(db)
            sessions = await session_repo.get_by_user(user_id, limit=100)

        audit_logger = get_audit_logger()
        audit_logger.log_export(
            user_id=user_id,
            export_type=export_format,
            record_count=len(records),
            filters_applied={"format": export_format},
        )

        if export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "ID",
                    "事件类型",
                    "题目内容",
                    "分类",
                    "难度",
                    "是否正确",
                    "用时(秒)",
                    "错误原因",
                    "创建时间",
                ]
            )
            for r in records:
                writer.writerow(
                    [
                        r.id,
                        r.event_type,
                        r.question_content[:100],
                        r.category,
                        r.difficulty,
                        "正确" if r.is_correct else ("错误" if r.is_correct is False else "未作答"),
                        r.time_spent or 0,
                        r.error_reason or "",
                        r.created_at.isoformat() if r.created_at else "",
                    ]
                )
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=learning_data.csv"
                },
            )
        else:
            user_data = {
                "user": {
                    "id": user.id if user else user_id,
                    "username": user.username if user else "",
                    "role": user.role if user else "student",
                },
                "learning_records": [
                    {
                        "id": r.id,
                        "event_type": r.event_type,
                        "question_content": r.question_content[:200],
                        "category": r.category,
                        "difficulty": r.difficulty,
                        "is_correct": r.is_correct,
                        "time_spent": r.time_spent,
                        "error_reason": r.error_reason,
                        "created_at": (
                            r.created_at.isoformat()
                            if r.created_at
                            else None
                        ),
                    }
                    for r in records
                ],
                "chat_sessions": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "message_count": s.message_count,
                        "status": s.status,
                        "created_at": (
                            s.created_at.isoformat()
                            if s.created_at
                            else None
                        ),
                    }
                    for s in sessions
                ],
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_records": len(records),
            }

            return JSONResponse(content=user_data)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"导出数据失败: {str(e)}"
        )


@router.delete("/purge")
async def purge_user_data(
    http_request: Request,
    confirm: str = Query("", description="输入 'DELETE_MY_DATA' 确认删除"),
):
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")

    if confirm != "DELETE_MY_DATA":
        raise HTTPException(
            status_code=400,
            detail="请确认删除操作：输入 confirm=DELETE_MY_DATA",
        )

    try:
        async with get_db_session() as db:
            record_repo = LearningRecordRepository(db)
            from app.data.models import LearningRecord
            from sqlalchemy import delete

            deleted_records = await db.execute(
                delete(LearningRecord).where(
                    LearningRecord.user_id == user_id
                )
            )
            await db.commit()

        audit_logger = get_audit_logger()
        audit_logger.log_deletion(
            user_id=user_id,
            resource_type="user_data",
            resource_id=user_id,
            reason="用户请求删除所有数据（隐私权）",
        )

        cache = get_cache_manager()
        await cache.invalidate_pattern(f"user:*:{user_id}*")

        return {
            "success": True,
            "message": "所有学习数据已删除",
            "deleted_records": deleted_records.rowcount,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"删除数据失败: {str(e)}"
        )