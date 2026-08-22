"""
依赖注入配置模块。

提供 FastAPI 依赖注入支持，降低模块耦合。
通过 Protocol 定义服务接口，支持测试时 Mock。

使用方式:
    from app.dependencies import get_llm_service, get_vector_store

    @router.post("/api/some")
    async def some_endpoint(
        llm: LLMServiceProtocol = Depends(get_llm_service),
        vector_store: VectorStoreProtocol = Depends(get_vector_store),
    ):
        ...
"""

import logging
from typing import Optional, Protocol, runtime_checkable

from fastapi import HTTPException

from app.config.settings import settings
from app.services.ai_capability import is_ai_available, raise_ai_unavailable

logger = logging.getLogger(__name__)


# ============================================================================
# 服务接口协议 (Protocol)
# ============================================================================

@runtime_checkable
class LLMServiceProtocol(Protocol):
    """LLM 服务接口协议。用于依赖注入和测试 Mock。"""

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tir_mode: bool = False,
    ) -> "LLMResponse":
        ...

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tir_mode: bool = False,
    ):
        ...

    @property
    def model(self) -> str:
        ...


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """向量存储服务接口协议。用于依赖注入和测试 Mock。"""

    async def initialize(self) -> None:
        ...

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list:
        ...

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        keywords: Optional[list[str]] = None,
        filter_metadata: Optional[dict] = None,
    ) -> list:
        ...

    async def add_question(
        self,
        question_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        ...

    async def delete_question(self, question_id: str) -> None:
        ...

    @property
    def is_initialized(self) -> bool:
        ...


# ============================================================================
# 依赖工厂函数
# ============================================================================

_llm_service: Optional[LLMServiceProtocol] = None
_vector_store: Optional[VectorStoreProtocol] = None


def get_llm_service() -> LLMServiceProtocol:
    """获取 LLM 服务实例（单例，延迟初始化）。

    当 AI 不可用（如 AI_ENABLED 为 false 或未配置 API Key）时抛出 503 异常。
    """
    if not is_ai_available():
        raise_ai_unavailable("llm")
    global _llm_service
    if _llm_service is None:
        from app.services.llm_service import LLMService
        _llm_service = LLMService(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.LLM_MODEL or "qwen-max",
            base_url=settings.LLM_API_BASE or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        logger.info("LLMService 已初始化（依赖注入）")
    return _llm_service


async def get_vector_store() -> VectorStoreProtocol:
    """获取向量存储实例（单例，延迟初始化）。"""
    global _vector_store
    if _vector_store is None:
        from app.services.vector_store import VectorStoreManager
        _vector_store = VectorStoreManager(
            persist_directory=settings.VECTOR_DB_PATH,
            collection_name="math_questions",
        )
        await _vector_store.initialize()
        logger.info("VectorStoreManager 已初始化（依赖注入）")
    return _vector_store


def get_agent():
    """获取全局 Agent 实例（由 main.py 在启动时设置）。

    当 AI 不可用（agent 为 None）时抛出 503 异常。
    """
    from main import agent
    if agent is None:
        raise_ai_unavailable("agent")
    return agent


def get_registry():
    """获取全局工具注册表实例。"""
    from main import registry
    return registry


def get_error_book_manager():
    """获取全局 ErrorBookManager 实例（使用数据库存储）。"""
    from main import error_book_manager
    return error_book_manager


def override_llm_service(mock_service: LLMServiceProtocol):
    """覆盖 LLM 服务实例（用于测试）。"""
    global _llm_service
    _llm_service = mock_service


def override_vector_store(mock_store: VectorStoreProtocol):
    """覆盖向量存储实例（用于测试）。"""
    global _vector_store
    _vector_store = mock_store


def reset_dependencies():
    """重置所有依赖（用于测试清理）。"""
    global _llm_service, _vector_store
    _llm_service = None
    _vector_store = None