"""
agent_core/classifier 包 — LLM复杂度分类路由。

提供基于快速LLM（qwen-turbo）的数学问题复杂度评估功能，
用于在 ReAct 和 Planned 两种执行策略之间进行智能路由。

核心组件:
    - ComplexityLevel: 复杂度分级枚举 (1-5)
    - LLMComplexityClassifier: LLM驱动的复杂度分类器
    - RobustOutputParser: 鲁棒的LLM输出解析器
    - ClassificationPromptTemplate: 分类Prompt模板 (位于 prompts/classifier_prompt.py)

使用示例:
    from langchain_openai import ChatOpenAI
    from agent_core.classifier import LLMComplexityClassifier

    fast_llm = ChatOpenAI(model="qwen-turbo", ...)
    classifier = LLMComplexityClassifier(llm=fast_llm)
    result = await classifier.classify("求∫x²dx")
    print(result.score)  # 输出: 3
"""

from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from prompts.classifier_prompt import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_HUMAN_TEMPLATE,
)
from agent_core.classifier.llm_classifier import (
    LLMComplexityClassifier,
    ClassificationResult,
    ClassifierConfig,
)

__all__ = [
    "ComplexityLevel",
    "ComplexityCategory",
    "level_to_strategy",
    "is_simple",
    "is_complex",
    "RobustOutputParser",
    "ClassificationPromptTemplate",
    "CLASSIFICATION_SYSTEM_PROMPT",
    "CLASSIFICATION_HUMAN_TEMPLATE",
    "LLMComplexityClassifier",
    "ClassificationResult",
    "ClassifierConfig",
]
