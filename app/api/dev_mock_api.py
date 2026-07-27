"""
Mock 测试接口（开发专用）。

提供：
- POST /api/dev/mock/trigger-question    模拟触发做题完成事件
- POST /api/dev/mock/trigger-mastery     模拟触发掌握度更新
- POST /api/dev/mock/trigger-chapter     模拟触发章节完成事件
- POST /api/dev/mock/generate-test-data  批量生成测试数据
"""

import logging
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from app.adapters.question_system.events import EventDispatcher
from app.adapters.question_system.mock_impl import _MOCK_CATEGORIES, _MOCK_KNOWLEDGE_POINTS
from app.services.memory_store import get_memory_store
from app.tasks.memory_tasks import get_async_memory_writer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev/mock", tags=["记忆系统-Mock测试"])

dispatcher = EventDispatcher()


@router.post("/trigger-question")
async def mock_trigger_question(
    request: Request,
    body: Dict[str, Any],
):
    """模拟触发做题完成事件，生成错题记忆。

    Request:
    {
        "user_id": "test001",
        "is_correct": false,
        "high_category": "高等数学",
        "category": "无穷级数",
        "difficulty": 3,
        "question_content": "（可选）自定义题目内容"
    }
    """
    user_id = body.get("user_id", "test001")
    is_correct = body.get("is_correct", False)
    high_category = body.get("high_category", "高等数学")
    category = body.get("category", "极限")
    difficulty = body.get("difficulty", 3)
    question_content = body.get("question_content", "")

    if not question_content:
        question_content = f"[Mock] 请计算{category}相关题目，难度等级{difficulty}"

    kps = _MOCK_KNOWLEDGE_POINTS.get(category, [])

    event_data = {
        "event_id": f"mock_evt_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "question_id": f"mock_q_{uuid.uuid4().hex[:8]}",
        "is_correct": is_correct,
        "score": 0 if not is_correct else 100,
        "high_category": high_category,
        "category": category,
        "knowledge_points": kps[:2] if kps else [category],
        "difficulty": difficulty,
        "user_answer": "用户模拟作答" if not is_correct else "正确解答",
        "correct_answer": "标准正确解答",
        "error_type": "概念混淆" if not is_correct else "",
        "finish_time": int(time.time()),
    }

    result = await dispatcher.dispatch("question-finish", event_data)

    return {
        "code": 0,
        "data": {
            "memory_id": result.get("memory_id"),
            "mock_event_id": event_data["event_id"],
            "is_correct": is_correct,
            "category": category,
        },
        "message": "模拟做题事件已触发",
    }


@router.post("/trigger-mastery")
async def mock_trigger_mastery(
    request: Request,
    body: Dict[str, Any],
):
    """模拟触发掌握度更新，测试里程碑生成。

    Request:
    {
        "user_id": "test001",
        "high_category": "高等数学",
        "category": "极限",
        "old_mastery_score": 0.35,
        "mastery_score": 0.75
    }
    """
    user_id = body.get("user_id", "test001")
    high_category = body.get("high_category", "高等数学")
    category = body.get("category", "极限")
    old_mastery = body.get("old_mastery_score", 0.35)
    new_mastery = body.get("mastery_score", 0.75)

    event_data = {
        "event_id": f"mock_evt_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "high_category": high_category,
        "category": category,
        "old_mastery_score": old_mastery,
        "mastery_score": new_mastery,
        "correct_rate": new_mastery,
        "total_questions": 30,
        "update_time": int(time.time()),
    }

    result = await dispatcher.dispatch("mastery-update", event_data)

    return {
        "code": 0,
        "data": result,
        "message": "模拟掌握度更新事件已触发",
    }


@router.post("/trigger-chapter")
async def mock_trigger_chapter(
    request: Request,
    body: Dict[str, Any],
):
    """模拟触发章节完成事件。

    Request:
    {
        "user_id": "test001",
        "chapter_name": "极限与连续",
        "high_category": "高等数学",
        "correct_rate": 0.78
    }
    """
    user_id = body.get("user_id", "test001")
    chapter_name = body.get("chapter_name", "极限与连续")
    high_category = body.get("high_category", "高等数学")
    correct_rate = body.get("correct_rate", 0.78)

    event_data = {
        "event_id": f"mock_evt_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "chapter_id": f"chap_{uuid.uuid4().hex[:8]}",
        "chapter_name": chapter_name,
        "high_category": high_category,
        "total_questions": 50,
        "correct_rate": correct_rate,
        "finish_time": int(time.time()),
    }

    result = await dispatcher.dispatch("chapter-complete", event_data)

    return {
        "code": 0,
        "data": result,
        "message": "模拟章节完成事件已触发",
    }


@router.post("/generate-test-data")
async def mock_generate_test_data(
    request: Request,
    body: Dict[str, Any],
):
    """批量生成测试用户的模拟记忆数据，用于压测。

    Request:
    {
        "user_count": 3,
        "memories_per_user": 10
    }
    """
    user_count = body.get("user_count", 3)
    memories_per_user = body.get("memories_per_user", 10)

    # 限制数量防止过载
    user_count = min(user_count, 10)
    memories_per_user = min(memories_per_user, 50)

    writer = get_async_memory_writer()
    categories = []
    for high_cat, cats in _MOCK_CATEGORIES.items():
        for cat in cats:
            categories.append((high_cat, cat))

    total_created = 0
    results = []

    for u in range(user_count):
        user_id = f"test_user_{u:04d}"

        for m in range(memories_per_user):
            high_cat, cat = random.choice(categories)
            kps = _MOCK_KNOWLEDGE_POINTS.get(cat, [])
            difficulty = random.randint(1, 5)
            is_correct = random.random() > 0.4

            if not is_correct:
                memory_id = await writer.write_error_memory(
                    user_id=user_id,
                    question_id=f"mock_q_{uuid.uuid4().hex[:8]}",
                    question_content=f"[Mock] {cat} 练习题 - 请计算并选择正确答案",
                    high_category=high_cat,
                    category=cat,
                    knowledge_points=kps[:2] if kps else [cat],
                    difficulty=difficulty,
                    user_answer="错误答案",
                    correct_answer="正确答案",
                    error_type=random.choice(["概念混淆", "计算错误", "公式记错"]),
                )
                if memory_id:
                    total_created += 1
            else:
                memory_id = await writer.write_conversation_memory(
                    user_id=user_id,
                    content=f"[Mock] 关于{cat}的对话记录，难度{difficulty}",
                    high_category=high_cat,
                    category=cat,
                    importance=0.5 + random.random() * 0.3,
                    tags=kps[:2] if kps else [cat],
                )
                if memory_id:
                    total_created += 1

        results.append({
            "user_id": user_id,
            "created": memories_per_user,
        })

    return {
        "code": 0,
        "data": {
            "total_created": total_created,
            "user_count": user_count,
            "memories_per_user": memories_per_user,
            "users": results,
        },
        "message": f"已为 {user_count} 个用户生成 {total_created} 条模拟记忆",
    }