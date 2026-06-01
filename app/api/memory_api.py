import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel, Field

from app.data.database import get_db_session
from app.data.repositories import LearningRecordRepository, QuestionRepository
from app.services.memory import (
    ShortTermMemory,
    LongTermMemory,
    MemoryRetrievalEngine,
    MemoryItem,
    RetrievalResult,
)
from app.services.cache import get_cache_manager
from app.security.audit import get_audit_logger
from app.security.access_control import require_permission, Permission

router = APIRouter(prefix="/api/memory", tags=["记忆系统"])

_short_term_store: dict[str, ShortTermMemory] = {}


def _get_or_create_short_term(session_id: str) -> ShortTermMemory:
    if session_id not in _short_term_store:
        _short_term_store[session_id] = ShortTermMemory()
    return _short_term_store[session_id]


class LearningEventRequest(BaseModel):
    event_type: str = Field(..., description="事件类型: ask | answer_correct | answer_wrong | review | skip")
    question_content: str = Field(..., description="题目内容")
    category: str = Field(..., description="知识点分类")
    sub_categories: Optional[str] = Field(None)
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    user_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    time_spent: Optional[int] = None
    tools_used: Optional[str] = None
    error_category: Optional[str] = None
    error_reason: Optional[str] = None
    metadata: Optional[dict] = Field(default_factory=dict)


class MemoryRetrieveParams(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=50)
    min_score: float = Field(0.3, ge=0, le=1)
    include_short_term: bool = True
    include_long_term: bool = True


@router.post("/events")
async def record_learning_event(request: LearningEventRequest, http_request: Request):
    user_id = getattr(http_request.state, "user_id", "anonymous")

    try:
        async with get_db_session() as db:
            repo = LearningRecordRepository(db)
            event_data = request.model_dump(exclude_none=True)
            event_data["user_id"] = user_id
            event_data["metadata_"] = event_data.pop("metadata", {})
            event_data["created_at"] = datetime.now(timezone.utc)

            record = await repo.create(**event_data)

        audit_logger = get_audit_logger()
        audit_logger.log_access(
            user_id=user_id,
            resource_type="learning_record",
            resource_id=str(record.id),
            action=f"record_{request.event_type}",
            ip_address=http_request.client.host if http_request.client else "",
        )

        profile_update = {"new_correct_rate": None, "weak_points_changed": False}

        return {
            "success": True,
            "event_id": record.id,
            "message": "学习事件已记录",
            "profile_update": profile_update,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录学习事件失败: {str(e)}")


@router.get("/retrieve")
async def retrieve_memory(
    http_request: Request,
    query: str = Query(..., min_length=1, description="搜索查询文本"),
    limit: int = Query(10, ge=1, le=50),
    min_score: float = Query(0.3, ge=0, le=1),
    include_short_term: bool = Query(True),
    include_long_term: bool = Query(True),
):
    user_id = getattr(http_request.state, "user_id", "anonymous")
    session_id = http_request.headers.get("X-Session-Id", "default")

    short_term_results = []
    long_term_results = []

    if include_short_term:
        short_term = _get_or_create_short_term(session_id)
        short_term_results = short_term.retrieve(query, top_k=limit)

    if include_long_term:
        cache = get_cache_manager()
        cache_key = f"memory:retrieve:{user_id}:{query}:{limit}"

        cached = await cache.get(cache_key)
        if cached is not None:
            long_term_results = cached
        else:
            long_term = LongTermMemory(get_db_session)
            long_term_results = await long_term.get_relevant_memories(
                user_id=user_id, query=query, limit=limit
            )
            await cache.set(cache_key, long_term_results, ttl=300)

    results = []

    for item in short_term_results:
        results.append(
            {
                "id": f"st_{item.signature}",
                "content": item.content[:200],
                "memory_type": item.memory_type,
                "category": item.category,
                "score": round(0.9 * 0.4, 2),
                "source": "short_term",
                "explanation": "来自当前会话的记忆",
                "timestamp": item.created_at.isoformat(),
            }
        )

    for item_dict in long_term_results:
        item_score = item_dict.get("relevance", 0) * 0.6
        if item_score >= min_score:
            results.append(
                {
                    "id": item_dict.get("id", str(uuid.uuid4())[:8]),
                    "content": item_dict.get("content", "")[:200],
                    "memory_type": item_dict.get("type", "unknown"),
                    "category": item_dict.get("category", ""),
                    "score": round(item_score, 2),
                    "source": "long_term",
                    "explanation": f'历史记忆 (匹配: {item_dict.get("relevance", 0):.2f})',
                    "timestamp": item_dict.get("timestamp"),
                }
            )

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    return {
        "query": query,
        "results": results,
        "statistics": {
            "total_found": len(results),
            "short_term_count": sum(
                1 for r in results if r["source"] == "short_term"
            ),
            "long_term_count": sum(
                1 for r in results if r["source"] == "long_term"
            ),
            "average_score": round(
                sum(r["score"] for r in results) / max(len(results), 1), 3
            ) if results else 0,
        },
    }


@router.get("/stats")
async def get_memory_stats(http_request: Request):
    session_id = http_request.headers.get("X-Session-Id", "default")
    short_term = _get_or_create_short_term(session_id)

    return {
        "short_term": short_term.stats,
        "session_id": session_id,
    }


@router.delete("/clear")
async def clear_short_term_memory(http_request: Request):
    session_id = http_request.headers.get("X-Session-Id", "default")
    if session_id in _short_term_store:
        _short_term_store[session_id].clear()

    return {
        "success": True,
        "message": "短期记忆已清空",
        "session_id": session_id,
    }


@router.post("/error-book/sync")
async def sync_error_book_to_skills(
    request: Request,
    error_entry: dict = None,
):
    user_id = getattr(request.state, "user_id", "anonymous")

    from app.services.error_book_sync import ErrorBookSkillSyncService
    sync_service = ErrorBookSkillSyncService()

    if error_entry:
        result = await sync_service.on_error_added(user_id, error_entry)
        return {"success": True, "action": "single_sync", **result}

    return {
        "success": False,
        "message": "需要提供 error_entry 数据",
    }


@router.post("/error-book/mastery")
async def toggle_error_mastery(
    request: Request,
    body: dict,
):
    user_id = getattr(request.state, "user_id", "anonymous")
    error_id = body.get("error_id")
    is_mastered = body.get("is_mastered", False)

    if not error_id:
        raise HTTPException(status_code=400, detail="error_id is required")

    from app.services.error_book_sync import ErrorBookSkillSyncService
    sync_service = ErrorBookSkillSyncService()
    result = await sync_service.on_error_mastery_toggled(
        user_id, str(error_id), bool(is_mastered)
    )

    return {"success": True, **result}


@router.post("/error-book/batch-sync")
async def batch_sync_error_book(
    request: Request,
    entries: List[dict],
):
    user_id = getattr(request.state, "user_id", "anonymous")

    from app.services.error_book_sync import ErrorBookSkillSyncService
    sync_service = ErrorBookSkillSyncService()
    result = await sync_service.batch_sync(user_id, entries)

    return {"success": True, **result}


@router.get("/skill-impact")
async def get_skill_impact_summary(request: Request):
    user_id = getattr(request.state, "user_id", "anonymous")

    from app.services.error_book_sync import ErrorBookSkillSyncService
    sync_service = ErrorBookSkillSyncService()
    summary = await sync_service.get_skill_impact_summary(user_id)

    return summary