"""
出题系统 Remote 适配器。

联调/生产阶段使用，通过 HTTP 事件接口与真实出题系统交互。
"""

import logging
from typing import Any, Dict, List, Optional

from app.adapters.question_system.base import BaseQuestionSystemAdapter

logger = logging.getLogger(__name__)


class RemoteQuestionSystemAdapter(BaseQuestionSystemAdapter):
    """Remote 出题系统适配器，对接真实出题系统 HTTP 接口。"""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self._api_key = api_key
        self._base_url = base_url
        logger.info("[Remote适配器] 初始化完成，对接真实出题系统")

    def get_question_info(self, question_id: str) -> Dict[str, Any]:
        # TODO: 实现 HTTP 调用出题系统接口
        logger.warning("[Remote适配器] get_question_info 尚未实现 HTTP 调用")
        return {
            "id": question_id,
            "content": "",
            "high_category": "",
            "category": "",
            "knowledge_points": [],
            "difficulty": 3,
            "is_active": True,
        }

    def get_user_mastery(self, user_id: str, category: str) -> Dict[str, Any]:
        logger.warning("[Remote适配器] get_user_mastery 尚未实现 HTTP 调用")
        return {"mastery_score": 0.5, "correct_rate": 0.5, "total_questions": 0}

    def get_user_mastery_all(self, user_id: str) -> Dict[str, Any]:
        logger.warning("[Remote适配器] get_user_mastery_all 尚未实现 HTTP 调用")
        return {}

    def get_user_chapter_progress(self, user_id: str, high_category: str) -> List[Dict[str, Any]]:
        logger.warning("[Remote适配器] get_user_chapter_progress 尚未实现 HTTP 调用")
        return []

    def get_user_recent_questions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        logger.warning("[Remote适配器] get_user_recent_questions 尚未实现 HTTP 调用")
        return []

    def check_health(self) -> bool:
        # TODO: 实现 HTTP 健康检查
        return True