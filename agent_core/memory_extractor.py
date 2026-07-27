"""
MemoryExtractor — 自动记忆提取器。

在Agent完成解题后，自动从执行结果中提取学习事件并持久化，
实现学习数据闭环。

架构位置：Agent执行流程
1. 用户输入 → TaskClassifier → 任务分类
2. TaskPlanner → 生成执行计划
3. ReActStrategy → 执行推理（工具调用 + 思考链）
4. 获得最终答案
5. [新增] MemoryExtractor → 提取学习事件
6. [新增] MemoryPersistenceFacade.record_event()
7. [新增] 自动触发技能重计算（每3条事件）
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 学习事件数据结构 ──


@dataclass
class LearningEvent:
    """从Agent执行结果中提取的学习事件。"""

    user_id: str
    event_type: str  # "problem_solving" | "concept_inquiry" | "error_analysis"
    question_content: str  # 用户原始输入（截断500字符）
    category: str  # 知识点分类（导数/极限/积分/级数/函数/代数/线性代数）
    sub_categories: List[str]
    user_answer: str  # Agent最终答案（截断200字符）
    correct_answer: str  # 标准答案（如有）
    difficulty: int = 3  # 默认中等，后续由DifficultyEstimator动态调整
    is_correct: Optional[bool] = None
    time_spent: float = 0.0  # 执行耗时（秒）
    hint_count: int = 0  # 提示次数
    tools_used: List[str] = field(default_factory=list)  # 使用的工具列表
    error_category: str = ""
    error_reason: str = ""
    correction_suggestion: str = ""
    metadata_: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""  # ISO格式时间戳

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，剔除None值和空列表（保留空字符串用于错误信息）。"""
        result = {}
        for key, value in asdict(self).items():
            if value is None:
                result[key] = ""
            elif isinstance(value, list) and not value:
                result[key] = []
            else:
                result[key] = value
        return result


# ── 记忆提取器 ──


class MemoryExtractor:
    """自动记忆提取器：从Agent执行结果中提取学习事件。"""

    _CATEGORY_KEYWORDS = {
        "导数": ["求导", "微分", "切线", "极值", "最值", "拐点", "单调"],
        "极限": ["极限", "收敛", "发散", "无穷", "连续"],
        "积分": ["积分", "定积分", "不定积分", "面积", "体积"],
        "级数": ["级数", "幂级数", "傅里叶"],
        "函数": ["函数", "定义域", "值域", "复合"],
        "代数": ["方程", "不等式"],
        "线性代数": ["矩阵", "行列式", "向量", "特征值"],
    }

    async def extract_from_agent_result(
        self,
        user_id: str,
        user_input: str,
        agent_result: Dict[str, Any],
        execution_time: float,
    ) -> Optional[LearningEvent]:
        """主入口：从Agent结果中提取学习事件。

        Args:
            user_id: 用户ID
            user_input: 用户原始输入文本
            agent_result: Agent执行结果，包含 answer / thoughts / metadata
            execution_time: 执行耗时（秒）

        Returns:
            LearningEvent 或 None（非数学解题类时返回None）
        """
        # Step 1: 判断是否数学解题类
        if not self._is_math_problem(user_input):
            return None

        # Step 2: 提取知识点分类
        category, sub_categories = self._extract_category(user_input)

        # Step 3: 提取工具调用
        tools_used = self._extract_tools_used(agent_result)

        # Step 4: 提取答案与正确性判断
        user_answer = agent_result.get("answer", "")
        correct_answer = (
            agent_result.get("metadata", {})
            .get("correct_answer", "")
        )
        is_correct = self._judge_correctness(user_answer, correct_answer)

        # Step 5: 提取错误信息
        error_category = error_reason = correction_suggestion = ""
        if is_correct is False:
            meta = agent_result.get("metadata", {})
            error_category = meta.get("error_category", "")
            error_reason = meta.get("error_reason", "")
            correction_suggestion = meta.get("correction_suggestion", "")

        # Step 6: 统计提示次数
        thoughts = agent_result.get("thoughts", [])
        hint_count = sum(
            1 for t in thoughts
            if t.get("type") == "observation" and "提示" in t.get("content", "")
        )

        # Step 7: 构建学习事件
        return LearningEvent(
            user_id=user_id,
            event_type="problem_solving",
            question_content=user_input[:500],
            category=category,
            sub_categories=sub_categories,
            difficulty=3,
            user_answer=user_answer[:200],
            correct_answer=correct_answer[:200],
            is_correct=is_correct,
            time_spent=execution_time,
            hint_count=hint_count,
            tools_used=tools_used,
            error_category=error_category,
            error_reason=error_reason,
            correction_suggestion=correction_suggestion,
            metadata_={
                "thought_count": len(thoughts),
                "tool_call_count": len(tools_used),
                "source": "auto_extractor",
            },
        )

    def _is_math_problem(self, text: str) -> bool:
        """判断是否为数学解题类问题（复用follow_up_recommender的逻辑）。"""
        from app.services.follow_up_recommender import is_math_problem
        return is_math_problem(text)

    def _extract_category(self, text: str):
        """从文本中提取知识点分类。"""
        category = "未知"
        subs = []
        for cat, keywords in self._CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                category = cat
                subs = [kw for kw in keywords if kw in text][:3]
                break
        return category, subs

    def _extract_tools_used(self, agent_result: Dict[str, Any]) -> List[str]:
        """从Agent结果中提取使用的工具列表。"""
        tools = []
        for t in agent_result.get("thoughts", []):
            if t.get("type") == "action" and t.get("tool"):
                tools.append(t["tool"])
        return list(set(tools))

    def _judge_correctness(
        self, user_answer: str, correct_answer: str
    ) -> Optional[bool]:
        """判断答案正确性（字符串匹配 + 数字交集兜底）。"""
        if not user_answer or not correct_answer:
            return None
        if user_answer.strip() == correct_answer.strip():
            return True
        user_nums = set(re.findall(r'\d+', user_answer))
        correct_nums = set(re.findall(r'\d+', correct_answer))
        if user_nums and correct_nums:
            return bool(user_nums & correct_nums)
        return None


# ── 单例导出 ──

_extractor_instance: Optional[MemoryExtractor] = None
_extractor_lock = object()


def get_memory_extractor() -> MemoryExtractor:
    """获取全局 MemoryExtractor 单例。"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = MemoryExtractor()
    return _extractor_instance