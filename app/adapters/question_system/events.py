"""
出题系统事件处理器。

接收出题系统推送的事件，分发到对应业务逻辑：
- question-finish → 错题记忆写入 / 知识点权重更新
- mastery-update → 画像增量更新 / 里程碑判定
- chapter-complete → 里程碑生成
- question-change → 记忆归档/更新
"""

import logging
import time
from typing import Any, Dict, Optional

from app.adapters.question_system.factory import get_question_system_adapter

logger = logging.getLogger(__name__)


class EventDispatcher:
    """事件分发器，将出题系统事件分发到记忆系统业务逻辑。"""

    def __init__(self):
        self._handlers = {
            "question-finish": self._handle_question_finish,
            "mastery-update": self._handle_mastery_update,
            "chapter-complete": self._handle_chapter_complete,
            "question-change": self._handle_question_change,
        }

    async def dispatch(self, event_type: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """分发事件到对应处理器。

        Args:
            event_type: 事件类型
            event_data: 事件数据

        Returns:
            dict: 处理结果
        """
        handler = self._handlers.get(event_type)
        if handler is None:
            logger.warning(f"[事件分发] 未知事件类型: {event_type}")
            return {"code": 1001, "message": f"未知事件类型: {event_type}"}

        try:
            return await handler(event_data)
        except Exception as e:
            logger.error(f"[事件分发] 处理事件失败: event_type={event_type}, error={e}")
            return {"code": 500, "message": f"处理事件失败: {str(e)}"}

    async def _handle_question_finish(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理单题作答完成事件。

        答错时生成错题记忆，答对时更新知识点权重。
        """
        user_id = data.get("user_id", "")
        is_correct = data.get("is_correct", False)
        question_id = data.get("question_id", "")

        if not user_id or not question_id:
            return {"code": 1001, "message": "缺少必要参数 user_id 或 question_id"}

        if is_correct:
            # 答对：更新知识点权重（异步处理）
            from app.services.memory_store import MemoryStore

            store = MemoryStore()
            await store.update_mastery_weight(
                user_id=user_id,
                high_category=data.get("high_category", ""),
                category=data.get("category", ""),
                is_correct=True,
            )
            return {"code": 0, "message": "知识点权重已更新", "memory_id": None}

        # 答错：生成错题记忆
        from app.services.memory_store import MemoryStore

        store = MemoryStore()
        memory_id = await store.create_error_memory(
            user_id=user_id,
            question_id=question_id,
            question_content=data.get("question_content", ""),
            high_category=data.get("high_category", ""),
            category=data.get("category", ""),
            knowledge_points=data.get("knowledge_points", []),
            difficulty=data.get("difficulty", 3),
            user_answer=data.get("user_answer", ""),
            correct_answer=data.get("correct_answer", ""),
            error_type=data.get("error_type", ""),
        )

        logger.info(f"[事件处理] 错题记忆已创建: memory_id={memory_id}, user={user_id}")
        return {"code": 0, "message": "错题记忆已创建", "memory_id": memory_id}

    async def _handle_mastery_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理知识点掌握度更新事件。

        触发画像增量更新和里程碑判定。
        """
        user_id = data.get("user_id", "")
        category = data.get("category", "")

        if not user_id or not category:
            return {"code": 1001, "message": "缺少必要参数"}

        from app.services.profile_service import ProfileService

        profile_service = ProfileService()
        await profile_service.incremental_update(
            user_id=user_id,
            high_category=data.get("high_category", ""),
            category=category,
            mastery_score=data.get("mastery_score", 0.0),
            correct_rate=data.get("correct_rate", 0.0),
        )

        # 里程碑判定：正确率从 <40% 提升至 >70%
        old_mastery = data.get("old_mastery_score", 0.0)
        new_mastery = data.get("mastery_score", 0.0)
        if old_mastery < 0.4 and new_mastery > 0.7:
            from app.services.memory_store import MemoryStore

            store = MemoryStore()
            await store.create_milestone_memory(
                user_id=user_id,
                milestone_type="mastery_improvement",
                description=f"知识点「{category}」正确率从 {old_mastery:.0%} 提升至 {new_mastery:.0%}",
                high_category=data.get("high_category", ""),
                category=category,
            )

        return {"code": 0, "message": "画像已更新"}

    async def _handle_chapter_complete(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理章节完成事件。

        生成里程碑记忆。
        """
        user_id = data.get("user_id", "")
        chapter_name = data.get("chapter_name", "")

        if not user_id or not chapter_name:
            return {"code": 1001, "message": "缺少必要参数"}

        from app.services.memory_store import MemoryStore

        store = MemoryStore()
        await store.create_milestone_memory(
            user_id=user_id,
            milestone_type="chapter_complete",
            description=f"完成章节「{chapter_name}」学习，正确率 {data.get('correct_rate', 0):.0%}",
            high_category=data.get("high_category", ""),
            category=chapter_name,
        )

        return {"code": 0, "message": "里程碑已创建"}

    async def _handle_question_change(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理题目基础信息变更事件。

        题目被删除时，关联记忆自动归档。
        """
        question_id = data.get("question_id", "")
        change_type = data.get("change_type", "")

        if not question_id:
            return {"code": 1001, "message": "缺少 question_id"}

        if change_type == "delete":
            from app.services.memory_store import MemoryStore

            store = MemoryStore()
            count = await store.archive_by_source_id(question_id)
            logger.info(f"[事件处理] 题目删除，已归档 {count} 条关联记忆: question_id={question_id}")

        return {"code": 0, "message": "变更已处理"}