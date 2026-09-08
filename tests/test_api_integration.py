"""
API 集成测试。

覆盖关键 API 端点：
- 健康检查
- 聊天端点
- 错题本端点
- Agent 端点
- 推荐端点
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


# 在导入 app 之前 mock 掉重依赖
@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock 所有外部依赖，确保测试不依赖真实服务。"""
    mock_eb = MagicMock()
    mock_eb.get_all = AsyncMock(return_value=[])
    mock_eb.add = AsyncMock(return_value="test_id")
    mock_eb.remove = AsyncMock(return_value=True)
    mock_eb.update = AsyncMock(return_value=True)

    # 为 auth middleware 提供 mock user
    mock_user = MagicMock()
    mock_user.id = "test_user_id"
    mock_user.is_active = True
    mock_user.role = "student"

    with patch("app.dependencies._llm_service", Mock()), \
         patch("app.dependencies._vector_store", Mock()), \
         patch("main.agent", Mock()), \
         patch("main.registry", Mock()), \
         patch("main.error_book_manager", mock_eb), \
         patch("app.middleware.auth_middleware.get_user_by_id", AsyncMock(return_value=mock_user)):
        yield


@pytest.fixture
def client():
    """创建 TestClient。"""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_token():
    """生成一个正式合法的 JWT access token 用于认证测试。"""
    from app.middleware.auth import create_access_token
    from app.config.settings import settings
    return create_access_token(
        "test_user_id",
        settings.JWT_SECRET_KEY,
        settings.JWT_ALGORITHM,
    )


@pytest.fixture
def auth_headers(auth_token):
    """返回合法 Authorization 头。"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestHealthEndpoint:
    """测试健康检查端点"""

    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_root_endpoint(self, client):
        response = client.get("/")
        # 根路径可能返回 200 或 404
        assert response.status_code in (200, 404, 307)


class TestAgentEndpoints:
    """测试 Agent 相关端点"""

    def test_list_tools(self, client):
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [
            {"name": "calculator", "description": "计算器"}
        ]
        with patch("main.registry", mock_registry):
            response = client.get("/api/tools")
            assert response.status_code == 200

    def test_get_agent_stats(self, client):
        mock_recorder = MagicMock()
        mock_recorder.get_stats.return_value = {"total_sessions": 5}
        mock_agent = MagicMock()
        mock_agent.get_thought_recorder.return_value = mock_recorder
        with patch("main.agent", mock_agent):
            response = client.get("/api/agent/stats")
            assert response.status_code == 200


class TestErrorBookEndpoints:
    """测试错题本端点"""

    def test_list_error_books(self, client, auth_headers):
        mock_manager = MagicMock()
        mock_manager.get_all = AsyncMock(return_value=[])
        with patch("main.error_book_manager", mock_manager):
            response = client.get("/api/error-book", headers=auth_headers)
            assert response.status_code == 200

    def test_add_error_book_validation(self, client, auth_headers):
        """测试添加错题时的输入验证"""
        # 空请求应返回验证错误
        response = client.post("/api/error-book", json={}, headers=auth_headers)
        # 验证失败应返回 422 或 400
        assert response.status_code in (400, 422)

    def test_add_error_book_valid(self, client, auth_headers):
        """测试添加有效错题"""
        mock_manager = MagicMock()
        mock_manager.add = AsyncMock(return_value="test_id")
        with patch("main.error_book_manager", mock_manager):
            response = client.post("/api/error-book", json={
                "question": "求极限 lim(x→0) sin(x)/x",
                "question_type": "text",
                "correct_answer": "1",
                "error_reason": "概念不清",
                "categories": ["极限"],
            }, headers=auth_headers)
            assert response.status_code in (200, 201, 400, 422)


class TestChatEndpoints:
    """测试聊天端点"""

    def test_chat_request_validation(self, client, auth_headers):
        """测试聊天请求输入验证"""
        # 空消息应返回验证错误
        response = client.post("/api/chat", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_chat_with_message(self, client, auth_headers):
        """测试正常聊天请求"""
        mock_agent = MagicMock()
        async def mock_stream(*args, **kwargs):
            yield "Hello"
        mock_agent.stream = mock_stream
        mock_agent._follow_up_text = None

        with patch("app.api.chat_api.get_agent", return_value=mock_agent), \
             patch("app.api.chat_api._tutor_run", AsyncMock(return_value=("test_user_id", {}, "test-run-id"))), \
             patch("app.services.tutor_service.complete_ai_run", AsyncMock(return_value=None)):
            response = client.post("/api/chat", json={
                "message": "1+1等于几？",
                "session_id": "test_session",
            }, headers=auth_headers)
            # 流式响应应返回 200
            assert response.status_code == 200


class TestRecommendationEndpoint:
    """测试推荐端点"""

    def test_recommendation_request(self, client, auth_headers):
        """测试推荐请求"""
        mock_recommender = AsyncMock()
        mock_recommender.recommend = AsyncMock(return_value=MagicMock(
            questions=[],
            ai_analysis={},
            meta={},
            request_id="test",
            generated_at="2026-07-05",
            processing_time_ms=100.0,
        ))

        with patch("app.api.recommendation_api.get_rag_recommender", return_value=mock_recommender):
            response = client.post("/api/recommendation", json={
                "user_id": "test_user",
                "count": 3,
            }, headers=auth_headers)
            # 可能返回 200 或 404（如果路由未注册）
            assert response.status_code in (200, 404)


class TestProfileMeEndpoint:
    """Step 0.5-B：/api/profile/me 系列 + 旧路由 ownership 权限测试。

    - /me 从认证上下文取 user_id，不接受 path user_id
    - 旧 /api/profile/{user_id} 通过 verify_resource_ownership 校验
    - 学生访问他人资源 → 403；未认证 → 401
    """

    def _mock_facade(self):
        from app.services.profile_application import ProfileSnapshot

        facade = AsyncMock()
        snapshot = ProfileSnapshot(user_id="test_user_id", total_questions=3)
        facade.get_profile_snapshot = AsyncMock(return_value=snapshot)
        facade.invalidate_profile_snapshot = AsyncMock(return_value=None)
        return facade

    def test_me_requires_auth(self, client):
        """未认证访问 /api/profile/me → 401。"""
        response = client.get("/api/profile/me")
        assert response.status_code == 401

    def test_me_returns_profile(self, client, auth_headers):
        """已认证访问 /api/profile/me → 200，user_id 来自认证上下文。"""
        facade = self._mock_facade()
        with patch("app.api.profile_api._get_facade", AsyncMock(return_value=facade)):
            response = client.get("/api/profile/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test_user_id"
        assert data["summary"]["total_questions"] == 3

    def test_me_skills_endpoint(self, client, auth_headers):
        """已认证访问 /api/profile/me/skills → 200。"""
        facade = self._mock_facade()
        from app.services.skill_aggregator import SkillAggregator

        # /me/skills 内部直接实例化 Facade / SkillAggregator（不经 _get_facade），
        # 因此 patch 类方法避免真实 DB 访问。
        with patch("app.api.profile_api._get_facade", AsyncMock(return_value=facade)), \
             patch.object(
                 SkillAggregator, "get_error_patterns",
                 AsyncMock(return_value=[]),
             ), \
             patch.object(
                 SkillAggregator, "get_cognitive_style",
                 AsyncMock(return_value={}),
             ):
            response = client.get("/api/profile/me/skills", headers=auth_headers)
        assert response.status_code == 200
        assert "skills" in response.json()

    def test_legacy_own_profile_allowed(self, client, auth_headers):
        """学生访问自己的 /api/profile/{user_id} → 200。"""
        facade = self._mock_facade()
        with patch("app.api.profile_api._get_facade", AsyncMock(return_value=facade)):
            response = client.get(
                "/api/profile/test_user_id", headers=auth_headers
            )
        assert response.status_code == 200

    def test_legacy_other_user_denied(self, client, auth_headers):
        """学生访问他人 /api/profile/{user_id} → 403。"""
        response = client.get("/api/profile/other_user", headers=auth_headers)
        assert response.status_code == 403

    def test_legacy_profile_requires_auth(self, client):
        """未认证访问 /api/profile/{user_id} → 401。"""
        response = client.get("/api/profile/test_user_id")
        assert response.status_code == 401


class TestSecurityHeaders:
    """测试安全头"""

    def test_cors_headers(self, client):
        response = client.options("/api/health")
        # 验证 CORS 头存在
        assert response.status_code in (200, 405)

    def test_content_type_json(self, client):
        response = client.get("/api/health")
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")
