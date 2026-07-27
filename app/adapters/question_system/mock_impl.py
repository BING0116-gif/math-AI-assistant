"""
出题系统 Mock 适配器。

开发/测试阶段使用，内置模拟数据，无需真实出题系统即可跑通全流程。
"""

import logging
import random
import time
from typing import Any, Dict, List, Optional

from app.adapters.question_system.base import BaseQuestionSystemAdapter

logger = logging.getLogger(__name__)

# 预置 Mock 用户数据
_MOCK_USERS = {
    "test001": "user001",
    "test002": "user002",
    "test003": "user003",
}

_MOCK_CATEGORIES = {
    "高等数学": [
        "极限与连续", "导数与微分", "积分学", "无穷级数", "微分方程",
    ],
    "线性代数": [
        "行列式", "矩阵", "向量空间", "特征值", "二次型",
    ],
    "概率论": [
        "古典概型", "随机变量", "数字特征", "大数定律", "参数估计",
    ],
}

_MOCK_KNOWLEDGE_POINTS = {
    "极限与连续": ["极限定义", "极限运算法则", "两个重要极限", "函数连续性", "间断点分类"],
    "导数与微分": ["导数定义", "求导法则", "高阶导数", "微分中值定理", "洛必达法则"],
    "积分学": ["不定积分", "定积分", "换元积分法", "分部积分法", "反常积分"],
    "无穷级数": ["数项级数", "幂级数", "傅里叶级数", "比值审敛法", "收敛半径"],
    "微分方程": ["一阶微分方程", "二阶微分方程", "线性微分方程组"],
    "行列式": ["行列式定义", "行列式性质", "克莱姆法则"],
    "矩阵": ["矩阵运算", "逆矩阵", "矩阵的秩"],
    "向量空间": ["向量组线性相关", "基与维数", "正交化"],
    "特征值": ["特征值与特征向量", "相似对角化"],
    "二次型": ["二次型标准形", "正定二次型"],
    "古典概型": ["排列组合", "条件概率", "全概率公式"],
    "随机变量": ["离散型随机变量", "连续型随机变量", "分布函数"],
    "数字特征": ["数学期望", "方差", "协方差"],
    "大数定律": ["切比雪夫不等式", "中心极限定理"],
    "参数估计": ["点估计", "区间估计", "极大似然估计"],
}


class MockQuestionSystemAdapter(BaseQuestionSystemAdapter):
    """Mock 出题系统适配器，内置模拟数据。"""

    def __init__(self):
        self._mock_questions: Dict[str, Dict[str, Any]] = {}
        self._init_mock_questions()
        logger.info("[Mock适配器] 初始化完成，内置 10 个测试用户模拟数据")

    def _init_mock_questions(self):
        """初始化 Mock 题目数据。"""
        qid = 0
        for high_cat, categories in _MOCK_CATEGORIES.items():
            for cat in categories:
                kps = _MOCK_KNOWLEDGE_POINTS.get(cat, [])
                for i in range(3):
                    qid += 1
                    qid_str = f"mock_q_{qid:04d}"
                    self._mock_questions[qid_str] = {
                        "id": qid_str,
                        "content": f"[Mock] {cat} 练习题 {i+1} - 请计算并选择正确答案",
                        "high_category": high_cat,
                        "category": cat,
                        "knowledge_points": kps[:2] if kps else [cat],
                        "difficulty": random.randint(1, 5),
                        "is_active": True,
                    }

    def get_question_info(self, question_id: str) -> Dict[str, Any]:
        question = self._mock_questions.get(question_id)
        if question:
            return question
        # 动态生成 fallback
        return {
            "id": question_id,
            "content": f"[Mock] 题目 {question_id}",
            "high_category": "高等数学",
            "category": "默认分类",
            "knowledge_points": ["默认知识点"],
            "difficulty": 3,
            "is_active": True,
        }

    def get_user_mastery(self, user_id: str, category: str) -> Dict[str, Any]:
        seed = hash(f"{user_id}:{category}")
        rng = random.Random(seed)
        return {
            "mastery_score": round(rng.uniform(0.3, 0.9), 2),
            "correct_rate": round(rng.uniform(0.3, 0.9), 2),
            "total_questions": rng.randint(5, 50),
        }

    def get_user_mastery_all(self, user_id: str) -> Dict[str, Any]:
        result = {}
        for high_cat, categories in _MOCK_CATEGORIES.items():
            cat_dict = {}
            for cat in categories:
                mastery = self.get_user_mastery(user_id, cat)
                cat_dict[cat] = mastery
            result[high_cat] = cat_dict
        return result

    def get_user_chapter_progress(self, user_id: str, high_category: str) -> List[Dict[str, Any]]:
        categories = _MOCK_CATEGORIES.get(high_category, [])
        result = []
        for i, cat in enumerate(categories):
            seed = hash(f"{user_id}:{cat}")
            rng = random.Random(seed)
            total = rng.randint(10, 30)
            completed = rng.randint(0, total)
            result.append({
                "chapter_id": f"chap_{i:03d}",
                "chapter_name": cat,
                "total_questions": total,
                "completed_count": completed,
                "correct_rate": round(rng.uniform(0.4, 0.9), 2),
            })
        return result

    def get_user_recent_questions(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        now = int(time.time())
        result = []
        for i in range(min(limit, 30)):
            high_cat = random.choice(list(_MOCK_CATEGORIES.keys()))
            cat = random.choice(_MOCK_CATEGORIES[high_cat])
            result.append({
                "question_id": f"mock_q_{random.randint(1, 100):04d}",
                "high_category": high_cat,
                "category": cat,
                "difficulty": random.randint(1, 5),
                "is_correct": random.random() > 0.4,
                "error_type": random.choice(["概念混淆", "计算错误", "审题不清", None]),
                "finish_time": now - random.randint(0, 86400 * 30),
            })
        return result

    def check_health(self) -> bool:
        return True