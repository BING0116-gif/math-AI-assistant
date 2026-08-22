"""
AI 能力边界测试。

覆盖：
- 无 API Key 启动（子进程隔离）
- AI_ENABLED=false 行为（子进程隔离）
- 非 AI 接口离线可用性
- AI unavailable API 契约（结构化 503）
- 禁止外部模型调用（forbidden constructor 拦截）
- 认证优先级（401 vs 503）
- AICapabilityState 状态计算
"""

import os
import sys
import json
import subprocess
import importlib
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from fastapi.testclient import TestClient

# ============================================================
# 辅助函数
# ============================================================

_SUBPROCESS_SCRIPT = os.path.join(
    os.path.dirname(__file__), "scripts", "offline_startup_check.py"
)


def _run_subprocess(mode: str) -> dict:
    """在独立子进程中运行离线启动检查，返回 JSON 结果。

    注意：app.application 的 logging.basicConfig 使用 force=True 输出到 stdout，
    因此子进程的 stdout 包含日志行 + JSON 行。JSON 总是最后一行。
    """
    env = os.environ.copy()
    env.pop("DASHSCOPE_API_KEY", None)
    env.pop("AI_ENABLED", None)

    if mode == "no-key":
        env["AI_ENABLED"] = "true"
        env["DASHSCOPE_API_KEY"] = ""  # 空字符串覆盖 .env 文件中的值
    elif mode == "disabled":
        env["AI_ENABLED"] = "false"
        env["DASHSCOPE_API_KEY"] = "test-key"
    else:
        raise ValueError(f"Unknown mode: {mode}")

    result = subprocess.run(
        [sys.executable, _SUBPROCESS_SCRIPT, f"--{mode}"],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )

    if result.returncode != 0:
        return {
            "success": False,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    # stdout 包含日志行 + JSON 块（多行缩进 JSON）
    # 通过查找第一个 "{" 定位 JSON 开始位置
    idx = result.stdout.find("{")
    if idx < 0:
        return {
            "success": False,
            "parse_error": "No JSON found in stdout",
            "stdout": result.stdout[:500],
        }

    json_str = result.stdout[idx:]
    try:
        data = json.loads(json_str)
        data["success"] = True
        return data
    except json.JSONDecodeError as e:
        return {"success": False, "parse_error": str(e), "stdout": result.stdout[:500]}


def _assert_unavailable_detail(response, expected_capability: str):
    """验证 AI 不可用响应 detail 是结构化格式。"""
    assert response.status_code == 503, (
        f"Expected 503, got {response.status_code}: {response.text[:200]}"
    )
    data = response.json()
    detail = data.get("detail", data)
    assert isinstance(detail, dict), f"Expected structured detail, got: {detail}"
    assert detail.get("code") == "AI_UNAVAILABLE", f"Expected AI_UNAVAILABLE, got: {detail}"
    assert detail.get("capability") == expected_capability
    assert detail.get("message") is not None
    assert detail.get("reason") is not None


# ============================================================
# 1. 无 API Key 真实启动（子进程隔离）
# ============================================================

class TestNoApiKeyStartupSubprocess:
    """测试无 API Key 时应用可完整启动（子进程隔离）。"""

    def test_no_key_app_imports_successfully(self):
        """新进程中没有 DASHSCOPE_API_KEY，真实 app import 成功。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')} {result.get('stdout', '')[:100]}"
        assert result.get("assembly_success") is True
        assert result.get("ai_available") is False
        assert result.get("ai_reason") == "missing_api_key"

    def test_no_key_math_agent_not_initialized(self):
        """无 Key 时 MathAgent 没有初始化。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("math_agent_not_imported") is True
        assert result.get("agent_is_none") is True

    def test_no_key_dynamic_llm_not_initialized(self):
        """无 Key 时 dynamic LLM factory 没有初始化。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("dynamic_llm_not_imported") is True

    def test_no_key_llm_service_not_initialized(self):
        """无 Key 时 LLMService 在 assembly 阶段没有初始化。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("llm_service_not_initialized") is True, (
            f"LLMService was initialized: {result.get('ai_modules_loaded', '')}"
        )

    def test_no_key_lifespan_entered(self):
        """无 Key 时 FastAPI lifespan 真实进入，health 正常。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')} {result.get('stdout', '')[:100]}"
        assert result.get("lifespan_entered") is True, (
            f"Lifespan not entered: {result.get('lifespan_error', '')}"
        )
        assert result.get("health_status") == 200

    def test_no_key_lifespan_no_llm_service(self):
        """无 Key 时 lifespan 内 LLMService 没有被初始化。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("lifespan_llm_service_not_initialized") is True, (
            f"LLMService was initialized during lifespan: {result.get('lifespan_new_ai_modules', '')}"
        )

    def test_no_key_health_returns_healthy(self):
        """无 Key 时 lifespan 内 /api/health 返回 200。"""
        result = _run_subprocess("no-key")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("health_status") == 200
        data = result.get("health_data_unavailable")
        if isinstance(data, dict):
            assert data.get("status") == "healthy"


# ============================================================
# 2. AI_ENABLED=false 真实启动（子进程隔离）
# ============================================================

class TestAiDisabledSubprocess:
    """测试 AI_ENABLED=false 时行为（子进程隔离）。"""

    def test_disabled_app_imports_successfully(self):
        """AI_ENABLED=false + 有 Key 时 app import 成功。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')} {result.get('stdout', '')[:100]}"
        assert result.get("assembly_success") is True

    def test_disabled_ai_reason(self):
        """AI_ENABLED=false 时 reason = disabled_by_config。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("ai_available") is False
        assert result.get("ai_reason") == "disabled_by_config"

    def test_disabled_math_agent_not_initialized(self):
        """AI_ENABLED=false 时 MathAgent 没有初始化。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("math_agent_not_imported") is True
        assert result.get("agent_is_none") is True

    def test_disabled_dynamic_llm_not_initialized(self):
        """AI_ENABLED=false 时 dynamic LLM factory 没有初始化。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("dynamic_llm_not_imported") is True

    def test_disabled_llm_service_not_initialized(self):
        """AI_ENABLED=false 时 LLMService 在 assembly 阶段没有初始化。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("llm_service_not_initialized") is True, (
            f"LLMService was initialized: {result.get('ai_modules_loaded', '')}"
        )

    def test_disabled_lifespan_entered(self):
        """AI_ENABLED=false + 有 Key 时 lifespan 真实进入，health 正常。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')} {result.get('stdout', '')[:100]}"
        assert result.get("lifespan_entered") is True, (
            f"Lifespan not entered: {result.get('lifespan_error', '')}"
        )
        assert result.get("health_status") == 200
        assert result.get("lifespan_llm_service_not_initialized") is True, (
            f"LLMService was initialized during lifespan: {result.get('lifespan_new_ai_modules', '')}"
        )

    def test_disabled_health_returns_healthy(self):
        """AI_ENABLED=false + 有 Key 时 lifespan 内 health 返回正常。"""
        result = _run_subprocess("disabled")
        assert result["success"], f"Subprocess failed: {result.get('parse_error', '')}"
        assert result.get("health_status") == 200


# ============================================================
# 3. 非 AI 接口离线可用性（Mock 外部依赖）
# ============================================================

class TestNonAiEndpoints:
    """测试 AI 不可用时非 AI 接口的可用性。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        # 重置 AI capability 缓存和依赖模块状态
        import app.services.ai_capability as cap_mod
        cap_mod.reset_for_test()
        import app.dependencies
        app.dependencies.reset_dependencies()

        self.mock_eb = MagicMock()
        self.mock_eb.get_all = AsyncMock(return_value=[])
        self.mock_eb.add = AsyncMock(return_value="test_id")
        self.mock_eb.remove = AsyncMock(return_value=True)
        self.mock_eb.update = AsyncMock(return_value=True)

        self.mock_user = MagicMock()
        self.mock_user.id = "test_user_id"
        self.mock_user.is_active = True

        async def _mock_auth_call(self_obj, scope, receive, send):
            scope["state"] = {"user_id": "test_user_id"}
            await self_obj.app(scope, receive, send)

        self.mock_auth = patch(
            "app.middleware.auth_middleware.AuthenticationMiddleware.__call__",
            _mock_auth_call,
        )
        self.mock_auth.start()

        # 注意：需要 patch 消费方模块的 is_ai_available 引用
        # 因为 chat_api/agent_api 等模块在 import 时已经绑定了原始函数引用
        with patch("app.dependencies._llm_service", Mock()), \
             patch("app.dependencies._vector_store", Mock()), \
             patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", self.mock_eb), \
             patch("app.api.chat_api.is_ai_available", return_value=False), \
             patch("app.api.agent_api.is_ai_available", return_value=False), \
             patch("app.api.chat_api.get_ai_capability") as mock_chat_cap, \
             patch("app.api.agent_api.get_ai_capability") as mock_agent_cap, \
             patch("app.dependencies.is_ai_available", return_value=False):
            # 构造一个不可用的 capability 状态
            from app.services.ai_capability import AICapabilityState
            mock_state = AICapabilityState(
                enabled_config=True, has_api_key=False,
                available=False, reason="missing_api_key",
            )
            mock_chat_cap.return_value = mock_state
            mock_agent_cap.return_value = mock_state
            from main import app
            self.client = TestClient(app)
            yield

        self.mock_auth.stop()

    def test_health_endpoint(self):
        """健康检查端点应正常工作。"""
        response = self.client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_health_detailed_endpoint(self):
        """详细健康检查应返回 AI 状态。"""
        response = self.client.get("/api/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "ai" in data
        assert data["ai"]["available"] is False

    def test_auth_flow(self):
        """认证流程应正常工作（Mock 数据库依赖）。"""
        mock_user = self.mock_user
        with patch("app.api.auth.authenticate_user", AsyncMock(return_value=mock_user)), \
             patch("app.api.auth.create_token_pair", AsyncMock(return_value=MagicMock(
                 model_dump=MagicMock(return_value={"access_token": "test", "refresh_token": "test", "token_type": "bearer"})
             ))):
            response = self.client.post("/api/auth/login", json={
                "username": "test_user",
                "password": "test_pass",
            })
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "success"

    def test_error_book_endpoint(self):
        """错题本接口应正常工作（需要认证已 Mock）。"""
        with patch("main.error_book_manager", self.mock_eb):
            response = self.client.get("/api/error-book")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_knowledge_endpoint(self):
        """知识库接口应正常响应（Mock 数据库依赖）。"""
        mock_session = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("app.api.knowledge_api.get_db_session", return_value=mock_cm), \
             patch("app.api.knowledge_api.list_published_courses", AsyncMock(return_value=[])):
            response = self.client.get("/api/knowledge/courses")
            assert response.status_code == 200
            data = response.json()
            assert "courses" in data


# ============================================================
# 4. AI unavailable API 契约（结构化 503）
# ============================================================

class TestAiUnavailableContract:
    """测试 AI 不可用时的 API 契约。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        import app.services.ai_capability as cap_mod
        cap_mod.reset_for_test()
        import app.dependencies
        app.dependencies.reset_dependencies()

        self.mock_eb = MagicMock()
        self.mock_eb.get_all = AsyncMock(return_value=[])

        async def _mock_auth_call(self_obj, scope, receive, send):
            scope["state"] = {"user_id": "test_user_id"}
            await self_obj.app(scope, receive, send)

        self.mock_auth = patch(
            "app.middleware.auth_middleware.AuthenticationMiddleware.__call__",
            _mock_auth_call,
        )
        self.mock_auth.start()

        # 构造一个不可用的 capability 状态
        from app.services.ai_capability import AICapabilityState
        mock_cap_state = AICapabilityState(
            enabled_config=True, has_api_key=False,
            available=False, reason="missing_api_key",
        )

        # Patch 所有消费方模块的引用
        with patch("app.dependencies._llm_service", Mock()), \
             patch("app.dependencies._vector_store", Mock()), \
             patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", self.mock_eb), \
             patch("app.api.chat_api.is_ai_available", return_value=False), \
             patch("app.api.chat_api.get_ai_capability", return_value=mock_cap_state), \
             patch("app.api.agent_api.is_ai_available", return_value=False), \
             patch("app.api.agent_api.get_ai_capability", return_value=mock_cap_state), \
             patch("app.dependencies.is_ai_available", return_value=False):
            from main import app
            self.client = TestClient(app)
            yield

        self.mock_auth.stop()

    # ---- Chat endpoints ----
    def test_chat_unavailable(self):
        response = self.client.post("/api/chat", json={
            "message": "1+1等于几？", "session_id": "test_session",
        })
        _assert_unavailable_detail(response, "chat")

    def test_recognize_unavailable(self):
        response = self.client.post("/api/recognize", json={
            "image": "data:image/png;base64,test", "session_id": "test_session",
        })
        _assert_unavailable_detail(response, "recognize")

    def test_chat_react_unavailable(self):
        response = self.client.post("/api/chat/react", json={
            "message": "帮我推导一下这个公式", "session_id": "test_session",
        })
        _assert_unavailable_detail(response, "chat")

    def test_chat_multimodal_unavailable(self):
        response = self.client.post("/api/chat/multimodal", json={
            "message": "解释这张图片", "image": "data:image/png;base64,test",
            "session_id": "test_session",
        })
        _assert_unavailable_detail(response, "multimodal")

    # ---- Agent endpoints ----
    def test_agent_thought_unavailable(self):
        response = self.client.get("/api/agent/thought/test_session")
        _assert_unavailable_detail(response, "agent")

    def test_agent_stats_unavailable(self):
        response = self.client.get("/api/agent/stats")
        _assert_unavailable_detail(response, "agent")


# ============================================================
# 5. 禁止外部模型调用（forbidden constructor 拦截）
# ============================================================

class TestNoExternalModelCalls:
    """测试离线模式下无外部模型调用。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_eb = MagicMock()
        self.mock_eb.get_all = AsyncMock(return_value=[])

    def _forbidden(self, *args, **kwargs):
        raise AssertionError(
            "AI runtime must not initialize while AI is unavailable"
        )

    def test_health_does_not_call_model(self):
        """健康检查不应触发任何模型初始化。

        在 import main 之前安装 forbidden constructor，确保覆盖 application startup。
        """
        # 重置 AI capability 缓存
        import app.services.ai_capability as cap_mod
        cap_mod.reset_for_test()

        # 在 import 前安装 forbidden constructor
        with patch("agent_core.MathAgent", self._forbidden), \
             patch("prompts.dynamic_params.init_dynamic_llm_factory", self._forbidden), \
             patch("app.services.llm_service.LLMService", self._forbidden), \
             patch("app.services.ai_capability.is_ai_available", return_value=False), \
             patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", self.mock_eb):
            # 隔离地重新导入 app.application
            for mod_name in list(sys.modules.keys()):
                if mod_name.startswith(("app.application",)):
                    del sys.modules[mod_name]

            import app.application as app_mod
            importlib.reload(app_mod)
            from main import app
            client = TestClient(app)

            response = client.get("/api/health")
            assert response.status_code == 200

            # 如果能到达这里，说明 forbidden constructor 没有被调用
            # 即 AI runtime 没有初始化

    def test_chat_returns_503_no_model_call(self):
        """AI 离线时聊天返回 503 且不调用 stream_handler。"""
        import app.services.ai_capability as cap_mod
        cap_mod.reset_for_test()
        import app.dependencies
        app.dependencies.reset_dependencies()

        async def _mock_auth_call(self_obj, scope, receive, send):
            scope["state"] = {"user_id": "test_user_id"}
            await self_obj.app(scope, receive, send)

        with patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", self.mock_eb), \
             patch("app.api.chat_api.is_ai_available", return_value=False), \
             patch("app.middleware.auth_middleware.AuthenticationMiddleware.__call__", _mock_auth_call):
            from main import app
            client = TestClient(app)

            with patch("app.api.chat_api.stream_agent_response") as mock_stream:
                response = client.post("/api/chat", json={
                    "message": "test", "session_id": "test_session",
                })
                assert response.status_code == 503, (
                    f"Expected 503, got {response.status_code}: {response.text[:200]}"
                )
                mock_stream.assert_not_called()


# ============================================================
# 6. 认证优先级测试
# ============================================================

class TestAuthPrecedence:
    """测试认证优先于 AI 可用性检查。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        import app.services.ai_capability as cap_mod
        cap_mod.reset_for_test()
        import app.dependencies
        app.dependencies.reset_dependencies()

        with patch("app.dependencies._llm_service", Mock()), \
             patch("app.dependencies._vector_store", Mock()), \
             patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", MagicMock()), \
             patch("app.api.chat_api.is_ai_available", return_value=False), \
             patch("app.dependencies.is_ai_available", return_value=False):
            from main import app
            self.client = TestClient(app)

    def test_unauthenticated_offline_returns_401(self):
        """AI offline + 无认证 -> 必须返回 401。"""
        response = self.client.post("/api/chat", json={
            "message": "test", "session_id": "test_session",
        })
        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated request, got {response.status_code}: {response.text}"
        )

    def test_authenticated_offline_returns_503(self):
        """AI offline + 合法认证 -> 503 AI_UNAVAILABLE。

        注意：此测试需要 mock auth middleware 的数据库查询。
        由于 auth middleware 在 __call__ 中调用 get_user_by_id()，
        且数据库不可用，需要 mock __call__ 让认证通过。

        同时 patch _check_ai_available 确保 AI 不可用返回 503。
        """
        from app.config.settings import settings as s
        from app.middleware.auth import create_access_token
        token = create_access_token(
            user_id="test_user_id",
            secret_key=s.JWT_SECRET_KEY,
        )

        # 创建一个 mock auth middleware __call__，让认证通过
        async def _auth_call_pass(self_obj, scope, receive, send):
            from starlette.requests import Request
            request = Request(scope)

            # 对 /api/health 等不需要认证的路径，直接通过
            if request.url.path in getattr(self_obj, '_no_auth_paths', set()):
                await self_obj.app(scope, receive, send)
                return

            # 验证 token
            auth_header = request.headers.get("Authorization", "")
            token_str = auth_header[7:] if auth_header.startswith("Bearer ") else ""
            from app.middleware.auth import verify_access_token
            user_id = verify_access_token(token_str, s.JWT_SECRET_KEY)
            if user_id is None:
                from starlette.responses import JSONResponse
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "认证令牌无效或已过期"},
                )
                await response(scope, receive, send)
                return

            scope["state"] = {"user_id": user_id}
            await self_obj.app(scope, receive, send)

        with patch(
            "app.middleware.auth_middleware.AuthenticationMiddleware.__call__",
            _auth_call_pass,
        ), patch(
            "app.api.chat_api._check_ai_available",
            side_effect=lambda cap: (_ for _ in ()).throw(
                __import__("fastapi").HTTPException(
                    status_code=503,
                    detail=__import__("app.models.ai_unavailable", fromlist=["AIUnavailableResponse"])
                    .AIUnavailableResponse.for_capability(cap, "missing_api_key").model_dump(),
                )
            ),
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "test", "session_id": "test_session"},
                headers={"Authorization": f"Bearer {token}"},
            )
        # 认证通过后，AI 不可用返回 503
        assert response.status_code == 503, (
            f"Expected 503, got {response.status_code}: {response.text[:200]}"
        )
        # 验证结构化 503
        data = response.json()
        detail = data.get("detail", data)
        assert isinstance(detail, dict)
        assert detail.get("code") == "AI_UNAVAILABLE"


# ============================================================
# 7. AICapabilityState 状态计算
# ============================================================

class TestAiCapabilityEdgeCases:
    """测试 AI 能力边界情况。"""

    def test_health_remains_healthy_when_ai_offline(self, monkeypatch):
        """AI 离线时整个应用仍应标记为 healthy。"""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "")  # 空字符串覆盖 .env 文件
        import app.config.settings
        importlib.reload(app.config.settings)
        import app.services.ai_capability
        importlib.reload(app.services.ai_capability)

        with patch("main.agent", Mock()), \
             patch("main.registry", Mock()), \
             patch("main.error_book_manager", MagicMock()):
            from main import app
            client = TestClient(app)
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "healthy"

    def test_ai_capability_state_compute(self, monkeypatch):
        """测试 AICapabilityState.compute() 各状态转换。"""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
        monkeypatch.setenv("AI_ENABLED", "true")
        import app.config.settings as settings_mod
        importlib.reload(settings_mod)
        import app.services.ai_capability as cap_mod
        importlib.reload(cap_mod)

        cap = cap_mod.get_ai_capability()
        assert hasattr(cap, "enabled_config")
        assert hasattr(cap, "has_api_key")
        assert hasattr(cap, "available")
        assert hasattr(cap, "reason")