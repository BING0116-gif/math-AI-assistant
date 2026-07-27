"""
出题系统适配器工厂。

通过环境变量 QUESTION_SYSTEM_MODE 自动选择实现：
- mock: 使用 MockQuestionSystemAdapter（开发/测试）
- remote: 使用 RemoteQuestionSystemAdapter（联调/生产）
"""

import os
import logging
from typing import Optional

from app.adapters.question_system.base import BaseQuestionSystemAdapter
from app.adapters.question_system.mock_impl import MockQuestionSystemAdapter
from app.adapters.question_system.remote_impl import RemoteQuestionSystemAdapter

logger = logging.getLogger(__name__)

_adapter_instance: Optional[BaseQuestionSystemAdapter] = None


def get_question_system_adapter() -> BaseQuestionSystemAdapter:
    """获取出题系统适配器实例（单例）。

    根据 QUESTION_SYSTEM_MODE 环境变量自动选择实现：
    - mock: Mock 模式（默认）
    - remote: Remote 模式
    """
    global _adapter_instance

    if _adapter_instance is not None:
        return _adapter_instance

    mode = os.getenv("QUESTION_SYSTEM_MODE", "mock").lower()

    if mode == "remote":
        api_key = os.getenv("QUESTION_SYSTEM_API_KEY", "")
        base_url = os.getenv("QUESTION_SYSTEM_BASE_URL", "")
        _adapter_instance = RemoteQuestionSystemAdapter(
            api_key=api_key, base_url=base_url
        )
        logger.info(f"[适配器工厂] 创建 Remote 适配器 (base_url={base_url})")
    else:
        _adapter_instance = MockQuestionSystemAdapter()
        logger.info("[适配器工厂] 创建 Mock 适配器")

    return _adapter_instance


def reset_adapter():
    """重置适配器实例（用于测试）。"""
    global _adapter_instance
    _adapter_instance = None