"""
记忆系统内部 API — Agent 专用接口。

提供：
- POST /api/internal/memory/retrieve    记忆检索主入口
- POST /api/internal/memory/write       异步记忆写入
- POST /api/internal/memory/update-strength 更新命中记忆强度
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from app.services.memory_retrieval import get_retrieval_engine
from app.services.memory_store import get_memory_store
from app.tasks.memory_tasks import get_async_memory_writer
from app.security.access_control import require_internal_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/memory", tags=["记忆系统-内部接口"])


@router.post("/retrieve")
async def internal_memory_retrieve(
    request: Request,
    body: Dict[str, Any],
):
    """记忆检索主入口（Agent 专用）。

    Request:
    {
        "user_id": "string",
        "query_text": "string",
        "top_k": 7,
        "memory_types": ["error", "conversation"],
        "high_category": "高等数学",
        "min_importance": 0.3
    }
    """
    # 内部接口鉴权
    require_internal_auth(request)

    user_id = body.get("user_id", "")
    query_text = body.get("query_text", "")
    top_k = body.get("top_k", 7)
    memory_types = body.get("memory_types")
    high_category = body.get("high_category")
    min_importance = body.get("min_importance", 0.0)

    if not user_id or not query_text:
        return {"code": 1001, "message": "缺少必要参数 user_id 或 query_text", "data": None}

    try:
        engine = get_retrieval_engine()
        result = await engine.retrieve(
            user_id=user_id,
            query_text=query_text,
            top_k=top_k,
            memory_types=memory_types,
            high_category=high_category,
            min_importance=min_importance,
        )

        memories_data = []
        for mem in result.memories:
            memories_data.append({
                "id": mem.id,
                "memory_type": mem.memory_type,
                "high_category": mem.high_category,
                "category": mem.category,
                "summary": mem.summary,
                "importance": mem.importance,
                "memory_strength": mem.memory_strength,
                "difficulty": mem.difficulty,
                "created_at": mem.created_at,
                "score": mem.score,
                "source": mem.source,
            })

        return {
            "code": 0,
            "data": {
                "memories": memories_data,
                "total": result.total,
                "stats": result.stats,
            },
        }

    except Exception as e:
        logger.error(f"[内部API] 记忆检索失败: {e}")
        return {"code": 500, "message": f"记忆检索失败: {str(e)}", "data": None}


@router.post("/write")
async def internal_memory_write(
    request: Request,
    body: Dict[str, Any],
):
    """异步记忆写入（Agent 专用）。

    Request:
    {
        "user_id": "string",
        "memory_type": "error",
        "raw_content": "题目原文...",
        "metadata": {
            "question_id": "q001",
            "high_category": "高等数学",
            "category": "无穷级数",
            "difficulty": 3,
            ...
        }
    }
    """
    require_internal_auth(request)

    user_id = body.get("user_id", "")
    memory_type = body.get("memory_type", "")
    raw_content = body.get("raw_content", "")
    metadata = body.get("metadata", {})

    if not user_id or not memory_type:
        return {"code": 1001, "message": "缺少必要参数", "data": None}

    try:
        writer = get_async_memory_writer()

        if memory_type == "error":
            memory_id = await writer.write_error_memory(
                user_id=user_id,
                question_id=metadata.get("question_id", ""),
                question_content=raw_content,
                high_category=metadata.get("high_category", ""),
                category=metadata.get("category", ""),
                knowledge_points=metadata.get("knowledge_points", []),
                difficulty=metadata.get("difficulty", 3),
                user_answer=metadata.get("user_answer", ""),
                correct_answer=metadata.get("correct_answer", ""),
                error_type=metadata.get("error_type", ""),
            )
        elif memory_type == "conversation":
            memory_id = await writer.write_conversation_memory(
                user_id=user_id,
                content=raw_content,
                high_category=metadata.get("high_category", ""),
                category=metadata.get("category", ""),
                importance=metadata.get("importance", 0.6),
                tags=metadata.get("tags", []),
            )
        elif memory_type == "milestone":
            memory_id = await writer.write_milestone_memory(
                user_id=user_id,
                milestone_type=metadata.get("milestone_type", ""),
                description=raw_content,
                high_category=metadata.get("high_category", ""),
                category=metadata.get("category", ""),
            )
        elif memory_type == "profile":
            memory_id = await writer.write_profile_memory(
                user_id=user_id,
                summary_text=raw_content,
                full_profile_json=metadata.get("full_profile_json", "{}"),
                high_category=metadata.get("high_category", ""),
                category=metadata.get("category", ""),
            )
        else:
            return {"code": 1001, "message": f"未知记忆类型: {memory_type}", "data": None}

        return {
            "code": 0,
            "data": {
                "memory_id": memory_id,
                "status": "pending" if memory_id is None else "active",
            },
        }

    except Exception as e:
        logger.error(f"[内部API] 记忆写入失败: {e}")
        return {"code": 500, "message": f"记忆写入失败: {str(e)}", "data": None}


@router.post("/update-strength")
async def internal_update_strength(
    request: Request,
    body: Dict[str, Any],
):
    """更新命中记忆强度（Agent 专用）。

    Request:
    {
        "user_id": "string",
        "memory_ids": [123, 456]
    }
    """
    require_internal_auth(request)

    user_id = body.get("user_id", "")
    memory_ids = body.get("memory_ids", [])

    if not user_id or not memory_ids:
        return {"code": 1001, "message": "缺少必要参数", "data": None}

    try:
        store = get_memory_store()
        updated_count = 0

        for mid in memory_ids:
            success = await store.update_memory_access(mid)
            if success:
                updated_count += 1

        return {
            "code": 0,
            "data": {
                "updated_count": updated_count,
                "total": len(memory_ids),
            },
        }

    except Exception as e:
        logger.error(f"[内部API] 更新记忆强度失败: {e}")
        return {"code": 500, "message": f"更新记忆强度失败: {str(e)}", "data": None}