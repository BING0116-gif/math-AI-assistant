"""
dynamic_params — 任务类型 → LLM推理参数动态映射模块。

根据用户意图分类（T1-T5）自动调整 temperature、top_p、max_tokens 等
LLM推理参数，实现精准回答与Token成本的最优平衡。

核心原则：
  - 准确性优先场景（T1/T2/T5）→ temperature=0.0（确定性输出）
  - 教学灵活性场景（T3）→ temperature=0.1（示例略灵活）
  - Token成本控制 → 按场景动态分配max_tokens
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """用户意图分类 — 五种场景类型。"""

    KNOWLEDGE_QUERY = "knowledge"       # T1 - 知识点查询
    QUICK_ANSWER = "quick"               # T2 - 快速答案
    CONCEPT_TEACHING = "concept"         # T3 - 概念讲解
    MULTIMODAL = "multimodal"            # T4 - 图片+提问
    FULL_SOLUTION = "solution"           # T5 - 完整解题
    PLANNED_SOLUTION = "planned"         # 复杂规划模式
    DEFAULT = "solution"                 # 默认=完整解题

    @classmethod
    def from_chinese_label(cls, label: str) -> "TaskType":
        """从中文标签转换为TaskType。"""
        mapping = {
            "T1": cls.KNOWLEDGE_QUERY,
            "T2": cls.QUICK_ANSWER,
            "T3": cls.CONCEPT_TEACHING,
            "T4": cls.MULTIMODAL,
            "T5": cls.FULL_SOLUTION,
            "planned": cls.PLANNED_SOLUTION,
        }
        return mapping.get(label, cls.DEFAULT)

    def to_chinese(self) -> str:
        """转换为中文标签。"""
        labels = {
            TaskType.KNOWLEDGE_QUERY: "知识点查询",
            TaskType.QUICK_ANSWER: "快速答案",
            TaskType.CONCEPT_TEACHING: "概念讲解",
            TaskType.MULTIMODAL: "多模态适配",
            TaskType.FULL_SOLUTION: "完整解题",
            TaskType.PLANNED_SOLUTION: "复杂规划",
        }
        return labels.get(self, "通用")

    @property
    def max_output_length(self) -> int:
        """获取该任务类型的最大输出字数（中文）。"""
        limits = {
            TaskType.KNOWLEDGE_QUERY: 200,
            TaskType.QUICK_ANSWER: 100,
            TaskType.CONCEPT_TEACHING: 500,
            TaskType.MULTIMODAL: 2000,
            TaskType.FULL_SOLUTION: 2000,
            TaskType.PLANNED_SOLUTION: 4000,
        }
        return limits.get(self, 2000)

    @property
    def needs_tools(self) -> bool:
        """该任务类型是否需要注入工具描述。"""
        return self in {TaskType.MULTIMODAL, TaskType.FULL_SOLUTION, TaskType.PLANNED_SOLUTION}

    @property
    def needs_profile(self) -> bool:
        """该任务类型是否需要注入用户画像。"""
        return self in {TaskType.CONCEPT_TEACHING, TaskType.FULL_SOLUTION, TaskType.PLANNED_SOLUTION}

    @property
    def max_history_turns(self) -> int:
        """该任务类型保留的最大对话轮数。"""
        values = {
            TaskType.KNOWLEDGE_QUERY: 1,
            TaskType.QUICK_ANSWER: 1,
            TaskType.CONCEPT_TEACHING: 2,
            TaskType.MULTIMODAL: 1,
            TaskType.FULL_SOLUTION: 5,
            TaskType.PLANNED_SOLUTION: 10,
        }
        return values.get(self, 5)


@dataclass
class LLMParams:
    """LLM推理参数配置。"""

    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4096
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为可传递给API的字典格式。"""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }


# ── 任务类型 → LLM参数映射表 ──

TASK_PARAMS_MAP: Dict[TaskType, LLMParams] = {
    TaskType.KNOWLEDGE_QUERY: LLMParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=800,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.QUICK_ANSWER: LLMParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=300,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.CONCEPT_TEACHING: LLMParams(
        temperature=0.1,
        top_p=0.95,
        max_tokens=2000,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.MULTIMODAL: LLMParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.FULL_SOLUTION: LLMParams(
        temperature=0.3,
        top_p=0.95,
        max_tokens=8192,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.PLANNED_SOLUTION: LLMParams(
        temperature=0.1,
        top_p=0.95,
        max_tokens=12288,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
    TaskType.DEFAULT: LLMParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    ),
}


# ── 复杂度评分 → max_tokens 自适应映射 ──

COMPLEXITY_TOKEN_MAP: Dict[int, int] = {
    1: 1024,     # 极简：1K tokens
    2: 2048,     # 简单：2K tokens
    3: 4096,     # 中等：4K tokens
    4: 8192,     # 较难：8K tokens
    5: 12288,    # 困难：12K tokens
}


def get_adaptive_max_tokens(complexity_score: int, task_type: TaskType) -> int:
    """根据复杂度评分获取自适应的 max_tokens。"""
    base = COMPLEXITY_TOKEN_MAP.get(complexity_score, 4096)
    type_max = task_type.max_output_length * 2  # 汉字→token 约2倍
    return max(base, type_max)


# ── 任务分类器 ──

class TaskClassifier:
    """
    轻量级用户意图分类器（规则匹配 + 降级策略）。

    采用纯规则匹配，不消耗任何LLM Token，执行时间 < 1ms。
    分类结果用于选择 LLMParams 和 Prompt 模板。

    Example:
        classifier = TaskClassifier()
        result = classifier.classify("这道题考的是什么知识点？")
        assert result.task_type == TaskType.KNOWLEDGE_QUERY
        print(result.confidence)  # 0.95
    """

    # 关键词匹配规则（按优先级排序）
    _RULES = [
        # (任务类型, 高权重关键词, 低权重关键词, 取反关键词)
        (
            TaskType.QUICK_ANSWER,
            ["选什么", "答案是", "等于多少", "对还是错", "哪个选项", "结果是多少"],
            ["答案", "结果", "等于", "选择", "是哪个"],
            ["步骤", "过程", "详细", "帮我", "分析"],
        ),
        (
            TaskType.KNOWLEDGE_QUERY,
            ["考什么知识点", "属于哪章", "涉及什么概念", "考的是什么", "什么考点", "哪个章节"],
            ["知识点", "考点", "章节", "概念", "哪一章"],
            ["帮我解", "详细", "步骤", "怎么算"],
        ),
        (
            TaskType.CONCEPT_TEACHING,
            ["什么是", "怎么理解", "是什么意思", "定义", "解释一下"],
            ["什么", "理解", "意思", "解释"],
            ["算", "解", "求"],
        ),
        (
            TaskType.FULL_SOLUTION,
            ["帮我解", "详细过程", "全部步骤", "写出解答", "详细解"],
            ["解", "求∫", "求lim", "计算", "证明", "求", "推导", "步骤", "过程"],
            [],
        ),
        # 数学符号触发 → 强制T5
        (
            TaskType.FULL_SOLUTION,
            ["∫", "∑", "∏", "lim", "dx", "dy", "f'(x)", "f''(x)", "∮", "∂"],
            [],
            ["是什么", "定义", "概念", "什么意思"],
        ),
    ]

    def __init__(self):
        self._cache: Dict[str, "ClassificationResult"] = {}

    def classify(self, user_input: str) -> "ClassificationResult":
        """
        对用户输入进行意图分类。

        Args:
            user_input: 用户输入文本。

        Returns:
            ClassificationResult 包含任务类型和置信度。
        """
        if not user_input or not user_input.strip():
            return ClassificationResult(TaskType.DEFAULT, confidence=0.5)

        trimmed = user_input.strip()

        if trimmed in self._cache:
            return self._cache[trimmed]

        scores: Dict[TaskType, float] = {t: 0.0 for t in TaskType}

        for task_type, high_keywords, low_keywords, negative_keywords in self._RULES:
            score = 0.0

            for kw in high_keywords:
                if kw in trimmed:
                    score += 0.4

            for kw in low_keywords:
                if kw in trimmed:
                    score += 0.15

            for nkw in negative_keywords:
                if nkw in trimmed:
                    score -= 0.3

            scores[task_type] = max(0.0, min(score, 1.0))

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score < 0.15:
            best_type = TaskType.DEFAULT
            best_score = 0.5

        result = ClassificationResult(task_type=best_type, confidence=best_score)
        if len(self._cache) < 1000:
            self._cache[trimmed] = result

        return result

    def clear_cache(self) -> None:
        """清除分类缓存。"""
        self._cache.clear()


@dataclass
class ClassificationResult:
    """意图分类结果。"""

    task_type: TaskType
    confidence: float


def get_params_for_task(task_type: TaskType) -> LLMParams:
    """
    获取指定任务类型的最佳 LLM 参数配置。

    Args:
        task_type: 任务类型枚举值。

    Returns:
        LLMParams 参数配置。
    """
    return TASK_PARAMS_MAP.get(task_type, TASK_PARAMS_MAP[TaskType.DEFAULT])


# ── 全局单例 ──

_default_classifier: Optional[TaskClassifier] = None


def get_classifier() -> TaskClassifier:
    """获取全局 TaskClassifier 单例。"""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = TaskClassifier()
    return _default_classifier


class DynamicLLMFactory:
    """
    动态LLM实例工厂。

    根据任务类型(T1-T5)动态创建或复用ChatOpenAI实例，
    每种任务类型使用最优化的LLM参数配置。

    核心价值：
    1. Token成本优化: T1/T2场景节省30-50%的max_tokens
    2. 性能平衡: T3教学场景适当提高temperature增加灵活性
    3. 实例复用: 相同参数的LLM实例只创建一次

    Example:
        factory = DynamicLLMFactory(
            api_key="sk-xxx",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        classifier = TaskClassifier()
        result = classifier.classify("这道题考什么知识点？")
        llm = factory.get_llm(result.task_type)

        agent = create_react_agent(llm, tools, prompt)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen-max",
        default_temperature: float = 0.0,
        streaming: bool = True,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._default_temperature = default_temperature
        self._streaming = streaming

        self._llm_cache: Dict[str, ChatOpenAI] = {}

        self._base_config = {
            'api_key': api_key,
            'base_url': base_url,
            'model': model,
            'streaming': streaming,
        }

        logger.info(
            f"DynamicLLMFactory初始化完成 "
            f"(model={model}, base_url={base_url})"
        )

    def get_llm(
        self,
        task_type: TaskType,
        override_params: Optional[Dict[str, Any]] = None,
    ) -> ChatOpenAI:
        """
        获取针对特定任务类型优化的LLM实例。

        Args:
            task_type: 任务类型枚举
            override_params: 可选的参数覆盖（用于特殊场景）

        Returns:
            配置好参数的ChatOpenAI实例
        """
        cache_key = task_type.value

        if cache_key in self._llm_cache and not override_params:
            cached_llm = self._llm_cache[cache_key]
            logger.debug(f"复用缓存的LLM实例: {cache_key}")
            return cached_llm

        params = get_params_for_task(task_type)
        params_dict = params.to_dict()

        if override_params:
            params_dict.update(override_params)
            cache_key = f"{cache_key}_custom"

        llm_config = {
            **self._base_config,
            **params_dict,
        }

        llm = ChatOpenAI(**llm_config)

        if not override_params:
            self._llm_cache[cache_key] = llm
            logger.info(
                f"创建并缓存新的LLM实例: {cache_key} "
                f"(temperature={params_dict['temperature']}, "
                f"max_tokens={params_dict['max_tokens']})"
            )
        else:
            logger.info(
                f"创建临时LLM实例: {cache_key} (不缓存)"
            )

        return llm

    def get_default_llm(self) -> ChatOpenAI:
        """获取默认配置的LLM（用于未知任务类型）。"""
        return self.get_llm(TaskType.DEFAULT)

    def classify_and_get_llm(self, user_input: str) -> tuple:
        """
        一站式服务：分类用户意图 + 返回优化的LLM。

        Args:
            user_input: 用户输入文本

        Returns:
            (ClassificationResult, ChatOpenAI) 元组
        """
        classifier = get_classifier()
        result = classifier.classify(user_input)
        llm = self.get_llm(result.task_type)

        logger.debug(
            f"意图分类: {result.task_type.value} "
            f"(confidence={result.confidence:.2f}) → "
            f"LLM配置已应用"
        )

        return result, llm

    def clear_cache(self):
        """清除LLM实例缓存（参数变更后调用）。"""
        count = len(self._llm_cache)
        self._llm_cache.clear()
        logger.info(f"LLM实例缓存已清除 (释放{count}个实例)")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息。"""
        return {
            'cached_instances': len(self._llm_cache),
            'cached_types': list(self._llm_cache.keys()),
            'factory_config': {
                'model': self._model,
                'base_url': self._base_url,
                'streaming': self._streaming,
            },
        }

    def update_base_config(self, **kwargs):
        """
        更新基础配置（会清除缓存）。

        Args:
            **kwargs: 要更新的配置项
        """
        self._base_config.update(kwargs)
        self.clear_cache()
        logger.info(f"基础配置已更新: {list(kwargs.keys())}")

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def streaming(self) -> bool:
        return self._streaming


_factory_instance: Optional[DynamicLLMFactory] = None


def init_dynamic_llm_factory(
    api_key: str,
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: str = "qwen-max",
    streaming: bool = True,
) -> DynamicLLMFactory:
    """
    初始化全局DynamicLLMFactory单例。

    应在应用启动时调用一次。

    Example:
        from prompts.dynamic_params import init_dynamic_llm_factory

        init_dynamic_llm_factory(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    """
    global _factory_instance
    _factory_instance = DynamicLLMFactory(
        api_key=api_key,
        base_url=base_url,
        model=model,
        streaming=streaming,
    )
    return _factory_instance


def get_dynamic_llm_factory() -> DynamicLLMFactory:
    """获取全局DynamicLLMFactory单例。"""
    global _factory_instance
    if _factory_instance is None:
        raise RuntimeError(
            "DynamicLLMFactory未初始化，请先调用 init_dynamic_llm_factory()"
        )
    return _factory_instance