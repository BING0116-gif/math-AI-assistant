"""
出题系统适配层抽象基类。

定义记忆系统与出题系统之间的标准化接口。
所有上层业务（记忆写入、画像生成、推荐排序）只依赖此抽象接口。
"""

from typing import Any, Dict, List, Optional


class BaseQuestionSystemAdapter:
    """出题系统适配器抽象基类。

    记忆系统通过此接口获取出题系统数据，不直接访问出题系统数据库。
    """

    def get_question_info(self, question_id: str) -> Dict[str, Any]:
        """获取题目基础信息（题干、知识点、难度）。

        Args:
            question_id: 出题系统题目 ID

        Returns:
            dict: {
                "id": str,
                "content": str,
                "high_category": str,
                "category": str,
                "knowledge_points": List[str],
                "difficulty": int,
                "is_active": bool
            }
        """
        raise NotImplementedError

    def get_user_mastery(self, user_id: str, category: str) -> Dict[str, Any]:
        """获取用户某知识点掌握度。

        Args:
            user_id: 用户 ID
            category: 知识点分类

        Returns:
            dict: {
                "mastery_score": float,  # 0-1
                "correct_rate": float,   # 0-1
                "total_questions": int
            }
        """
        raise NotImplementedError

    def get_user_mastery_all(self, user_id: str) -> Dict[str, Any]:
        """获取用户所有知识点掌握度。

        Args:
            user_id: 用户 ID

        Returns:
            dict: {
                "high_category": {
                    "category": {
                        "mastery_score": float,
                        "correct_rate": float,
                        "total_questions": int
                    }
                }
            }
        """
        raise NotImplementedError

    def get_user_chapter_progress(self, user_id: str, high_category: str) -> List[Dict[str, Any]]:
        """获取用户章节学习进度。

        Args:
            user_id: 用户 ID
            high_category: 一级分类

        Returns:
            List[dict]: [
                {
                    "chapter_id": str,
                    "chapter_name": str,
                    "total_questions": int,
                    "completed_count": int,
                    "correct_rate": float
                }
            ]
        """
        raise NotImplementedError

    def get_user_recent_questions(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取用户最近做题记录。

        Args:
            user_id: 用户 ID
            limit: 返回条数

        Returns:
            List[dict]: [
                {
                    "question_id": str,
                    "high_category": str,
                    "category": str,
                    "difficulty": int,
                    "is_correct": bool,
                    "error_type": Optional[str],
                    "finish_time": int
                }
            ]
        """
        raise NotImplementedError

    def check_health(self) -> bool:
        """检查出题系统是否可用。"""
        raise NotImplementedError