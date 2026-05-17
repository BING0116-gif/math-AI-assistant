"""
prompts 包 — Prompt 工程管理模块（v3.0 四层架构）。

提供:
- SystemPromptManager: 四层架构动态 System Prompt
- ReActPromptTemplate: 精简版 ReAct 工具调用指令
- TaskClassifier / TaskType / LLMParams: 意图分类与动态参数调整
"""

from prompts.system_prompt import SystemPromptManager
from prompts.react_prompt import ReActPromptTemplate
from prompts.dynamic_params import (
    TaskClassifier,
    ClassificationResult,
    TaskType,
    LLMParams,
    get_params_for_task,
    get_classifier,
    TASK_PARAMS_MAP,
)

__all__ = [
    "SystemPromptManager",
    "ReActPromptTemplate",
    "TaskClassifier",
    "ClassificationResult",
    "TaskType",
    "LLMParams",
    "get_params_for_task",
    "get_classifier",
    "TASK_PARAMS_MAP",
]