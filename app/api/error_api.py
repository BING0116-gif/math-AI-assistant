"""
错题本相关 API 路由。

包含 /api/error-book 的 CRUD 端点。
"""

import logging
import uuid
import re as _re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.middleware.security import (
    validate_input,
    validate_request_data,
    SecurityValidationError,
)
from data_processing.validators import ErrorBookValidator
from data_processing.formatters import ErrorBookFormatter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["error-book"])


class ErrorItemRequest(BaseModel):
    id: str = ""
    question: str
    question_type: str = "text"
    image_path: str | None = None
    error_reason: str = ""
    categories: list[str] = []
    original_answer: str = ""
    correct_answer: str = ""
    notes: str = ""
    added_at: str = ""
    mastery_level: int = 3
    is_mastered: bool = False


class ErrorUpdateRequest(BaseModel):
    question: str | None = None
    question_type: str | None = None
    image_path: str | None = None
    error_reason: str | None = None
    categories: list[str] | None = None
    original_answer: str | None = None
    correct_answer: str | None = None
    notes: str | None = None
    added_at: str | None = None
    mastery_level: int | None = None
    is_mastered: bool | None = None


class ErrorReviewRequest(BaseModel):
    event_type: str
    event_id: str = ""
    attempt_id: str
    details: dict = Field(default_factory=dict)


def get_error_book_manager():
    """获取全局 ErrorBookManager 实例（由 main.py 在启动时设置）。"""
    from main import error_book_manager
    return error_book_manager


def _get_user_id(request: Request) -> str:
    """从认证上下文获取用户 ID。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return str(user_id)


@router.get("/api/error-book")
async def get_error_book(request: Request):
    try:
        user_id = _get_user_id(request)
        errors = await get_error_book_manager().get_all(user_id)
        return [error.to_dict() for error in errors]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/api/error-book")
async def add_error(request: Request, body: ErrorItemRequest):
    from error_book import ErrorItem

    try:
        user_id = _get_user_id(request)
        raw_data = body.dict()
        try:
            validated_data = validate_request_data(raw_data, max_length=settings.INPUT_MAX_LENGTH, skip_sql_check=True)
        except SecurityValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        is_valid, validation_errors = ErrorBookValidator.validate(validated_data)

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"数据验证失败: {'; '.join(validation_errors)}",
            )

        correct_answer = validated_data.get("correct_answer", "")

        _incomplete_patterns = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
            r'^\*\*正确答案\*\*[：:]\s*$',
            r'^答案[：:]\s*$',
            r'^最终答案[：:]\s*$',
        ]

        _is_incomplete_answer = any(
            _re.match(pattern, correct_answer.strip(), _re.IGNORECASE)
            for pattern in _incomplete_patterns
        )

        if _is_incomplete_answer:
            logger.warning(
                f"检测到不完整的答案解析 (ID: {validated_data.get('id', 'unknown')}) - "
                f"答案内容只有标题标记，无实际解析内容。"
            )
            _warning_note = (
                "[WARN] [系统警告] 此题的答案解析可能不完整\n"
                "原因: 检测到答案只包含标题标记（如'【最终答案】'），缺少实际解题过程\n"
                "建议: 请重新添加此错题，或手动补充完整解析"
            )
            existing_notes = validated_data.get("notes", "") or ""
            validated_data["notes"] = f"{existing_notes}\n\n{_warning_note}" if existing_notes else _warning_note

        formatted_data = ErrorBookFormatter.format(validated_data)

        error_item = ErrorItem(
            id=formatted_data.get("id", ""),
            question=formatted_data.get("question", ""),
            question_type=formatted_data.get("question_type", "text"),
            image_path=formatted_data.get("image_path"),
            error_reason=formatted_data.get("error_reason", ""),
            categories=formatted_data.get("categories", []),
            original_answer=formatted_data.get("original_answer", ""),
            correct_answer=formatted_data.get("correct_answer", ""),
            notes=formatted_data.get("notes", ""),
            added_at=formatted_data.get("added_at", ""),
            mastery_level=formatted_data.get("mastery_level", 3),
            is_mastered=formatted_data.get("is_mastered", False),
        )

        error_id = await get_error_book_manager().add(user_id, error_item)

        return {
            "id": error_id,
            "status": "success",
            "message": "错题添加成功",
            "data": {
                **error_item.to_dict(),
                "display_question": formatted_data.get("display_question", ""),
                "recognized_text": formatted_data.get("recognized_text", ""),
                "answer_preview": formatted_data.get("answer_preview", ""),
                "has_image": formatted_data.get("has_image", False),
                "categories": formatted_data.get("categories", []),
            },
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/api/error-book/{error_id}")
async def update_error(error_id: str, request: Request, body: ErrorUpdateRequest):
    try:
        user_id = _get_user_id(request)
        try:
            validated_id = validate_input(error_id, "error_id", max_length=64)
        except SecurityValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        update_data = {}
        fields = [
            "question", "question_type", "image_path", "error_reason",
            "categories", "original_answer", "correct_answer", "notes",
            "added_at", "mastery_level", "is_mastered",
        ]
        for field in fields:
            value = getattr(body, field, None)
            if value is not None:
                try:
                    update_data[field] = validate_input(value, field, max_length=settings.INPUT_MAX_LENGTH)
                except SecurityValidationError as e:
                    raise HTTPException(status_code=400, detail=str(e))

        if update_data.get("is_mastered") is True:
            from sqlalchemy import select
            from app.data.database import get_db_session
            from app.data.models import ErrorItem as ErrorItemModel
            async with get_db_session() as db:
                source = await db.scalar(select(ErrorItemModel.source).where(
                    ErrorItemModel.user_id == user_id,
                    ErrorItemModel.item_id == validated_id,
                ))
            if source == "attempt":
                raise HTTPException(
                    status_code=409,
                    detail="自动错题必须完成原题、变式和间隔复测后才能毕业",
                )
        success = await get_error_book_manager().update(user_id, validated_id, **update_data)
        return {"success": success}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/api/error-book/{error_id}")
async def delete_error(error_id: str, request: Request):
    try:
        validated_id = validate_input(error_id, "error_id", max_length=64)
    except SecurityValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        user_id = _get_user_id(request)
        success = await get_error_book_manager().remove(user_id, validated_id)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/api/error-book/{error_id}/review")
async def record_error_review(error_id: str, request: Request, body: ErrorReviewRequest):
    """Record immutable review evidence and apply the guarded state transition."""
    from app.data.database import get_db_session
    from app.services.error_review import record_review_evidence

    user_id = _get_user_id(request)
    try:
        validated_id = validate_input(error_id, "error_id", max_length=64)
        async with get_db_session() as db:
            from sqlalchemy import select
            from app.data.models import ErrorItem as ErrorItemModel, PracticeAttempt, PracticeSession

            owned_item = await db.scalar(select(ErrorItemModel).where(
                ErrorItemModel.user_id == user_id,
                ErrorItemModel.item_id == validated_id,
            ))
            if owned_item is None:
                raise LookupError("error item not found")
            attempt_row = (await db.execute(
                select(PracticeAttempt, PracticeSession)
                .join(PracticeSession, PracticeSession.id == PracticeAttempt.session_id)
                .where(
                    PracticeAttempt.id == body.attempt_id,
                    PracticeAttempt.user_id == user_id,
                    PracticeAttempt.correct.is_(True),
                )
            )).one_or_none()
            if attempt_row is None:
                raise ValueError("review evidence must reference your own correct attempt")
            attempt, review_session = attempt_row
            config = review_session.config_snapshot or {}
            if body.event_type == "original_correct" and attempt.question_id != owned_item.question_id:
                raise ValueError("original review attempt does not match the error question")
            if body.event_type in {"variant_correct", "spaced_correct"}:
                if config.get("review_kind") != body.event_type or config.get("error_item_id") != validated_id:
                    raise ValueError("review attempt is not bound to this error item and review stage")
            item = await record_review_evidence(
                db, user_id=user_id, item_id=validated_id,
                event_type=body.event_type,
                event_id=body.event_id or str(uuid.uuid4()),
                attempt_id=attempt.id, details=body.details,
            )
            await db.flush()
            return {
                "id": item.item_id, "review_state": item.review_state,
                "is_mastered": item.is_mastered,
                "last_reviewed_at": item.last_reviewed_at,
            }
    except LookupError:
        raise HTTPException(status_code=404, detail="错题不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
