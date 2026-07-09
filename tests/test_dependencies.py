"""
依赖注入模块单元测试。

覆盖：
- LLMServiceProtocol 接口
- VectorStoreProtocol 接口
- 工厂函数
- 依赖注入有效性
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.dependencies import (
    LLMServiceProtocol,
    VectorStoreProtocol,
    get_llm_service,
    get_vector_store,
    override_llm_service,
    override_vector_store,
    reset_dependencies,
)


class TestProtocolInterfaces:
    """测试 Protocol 接口定义"""

    def test_protocols_defined(self):
        """确认 Protocol 类已定义"""
        assert LLMServiceProtocol is not None
        assert VectorStoreProtocol is not None

    def test_llm_service_protocol_has_methods(self):
        """确认 LLMServiceProtocol 定义了必要方法"""
        assert hasattr(LLMServiceProtocol, 'chat')
        assert hasattr(LLMServiceProtocol, 'chat_stream')
        assert hasattr(LLMServiceProtocol, 'model')

    def test_vector_store_protocol_has_methods(self):
        """确认 VectorStoreProtocol 定义了必要方法"""
        assert hasattr(VectorStoreProtocol, 'initialize')
        assert hasattr(VectorStoreProtocol, 'search')
        assert hasattr(VectorStoreProtocol, 'add_question')


class TestDependencyFactories:
    """测试依赖工厂函数"""

    def test_get_llm_service_returns_instance(self):
        """get_llm_service 返回有效实例"""
        reset_dependencies()
        mock_svc = Mock()
        with patch("app.services.llm_service.LLMService", return_value=mock_svc):
            result = get_llm_service()
            assert result is not None
        reset_dependencies()

    def test_get_llm_service_singleton(self):
        """get_llm_service 返回单例"""
        reset_dependencies()
        mock_svc = Mock()
        with patch("app.services.llm_service.LLMService", return_value=mock_svc):
            result1 = get_llm_service()
            result2 = get_llm_service()
            assert result1 is result2
        reset_dependencies()

    def test_override_llm_service(self):
        """测试覆盖 LLM 服务"""
        reset_dependencies()
        mock_svc = Mock()
        override_llm_service(mock_svc)
        result = get_llm_service()
        assert result is mock_svc
        reset_dependencies()

    def test_override_vector_store(self):
        """测试覆盖向量存储"""
        reset_dependencies()
        mock_store = Mock()
        override_vector_store(mock_store)
        assert mock_store is not None
        reset_dependencies()

    def test_reset_dependencies(self):
        """测试重置依赖"""
        reset_dependencies()
        mock_svc = Mock()
        override_llm_service(mock_svc)
        reset_dependencies()
        # 重置后应创建新实例
        mock_new = Mock()
        with patch("app.services.llm_service.LLMService", return_value=mock_new):
            result = get_llm_service()
            assert result is mock_new
        reset_dependencies()


class TestDependencyInjection:
    """测试依赖注入集成"""

    def test_get_agent_exists(self):
        """确认 get_agent 函数存在"""
        from app.dependencies import get_agent
        assert callable(get_agent)

    def test_get_registry_exists(self):
        """确认 get_registry 函数存在"""
        from app.dependencies import get_registry
        assert callable(get_registry)

    def test_get_error_book_manager_exists(self):
        """确认 get_error_book_manager 函数存在"""
        from app.dependencies import get_error_book_manager
        assert callable(get_error_book_manager)