from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.error_api import get_error_book
from app.config.middleware_config import middleware_config
from app.security.access_control import require_admin_role, verify_resource_ownership


def _request(user=None, path="/") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "state": {},
    }
    request = Request(scope)
    if user is not None:
        request.state.current_user = user
        request.state.user_id = user.id
    return request


@pytest.mark.asyncio
async def test_unauthenticated_error_book():
    with pytest.raises(HTTPException) as exc:
        await get_error_book(_request(path="/api/error-book"))
    assert exc.value.status_code == 401
    assert "/api/error-book" not in middleware_config.NO_AUTH_PATHS
    assert "/api/recognize" not in middleware_config.NO_AUTH_PATHS
    assert "/api/agent/thought/" not in middleware_config.NO_AUTH_PATHS


@pytest.mark.asyncio
async def test_cross_user_error_book(monkeypatch):
    from app.api import error_api

    class Item:
        def __init__(self, owner):
            self.owner = owner

        def to_dict(self):
            return {"owner": self.owner}

    class Manager:
        async def get_all(self, user_id):
            return [Item(user_id)]

    monkeypatch.setattr(error_api, "get_error_book_manager", lambda: Manager())
    result_a = await error_api.get_error_book(
        _request(SimpleNamespace(id="user-a", role="student"))
    )
    result_b = await error_api.get_error_book(
        _request(SimpleNamespace(id="user-b", role="student"))
    )
    assert result_a == [{"owner": "user-a"}]
    assert result_b == [{"owner": "user-b"}]


def test_cross_user_profile():
    request = _request(SimpleNamespace(id="user-b", role="student"))
    with pytest.raises(HTTPException) as exc:
        verify_resource_ownership(request, "user-a")
    assert exc.value.status_code == 403


def test_dashboard_admin_only():
    student_request = _request(SimpleNamespace(id="student", role="student"))
    with pytest.raises(HTTPException) as exc:
        require_admin_role(student_request)
    assert exc.value.status_code == 403

    admin_request = _request(SimpleNamespace(id="admin", role="admin"))
    require_admin_role(admin_request)


def test_mock_api_debug_only():
    from app.router_registration import register_debug_routes

    class FakeApp:
        def __init__(self):
            self.routers = []

        def include_router(self, router):
            self.routers.append(router)

    production = FakeApp()
    router = object()
    register_debug_routes(production, False, router)
    assert production.routers == []

    development = FakeApp()
    register_debug_routes(development, True, router)
    assert development.routers == [router]


@pytest.mark.asyncio
async def test_refresh_token_revocation(monkeypatch):
    from app.api import auth as auth_api

    revoked = set()

    async def fake_revoke(token, *_args):
        revoked.add(token)
        return True

    async def fake_refresh(token, *_args):
        return None if token in revoked else object()

    monkeypatch.setattr(auth_api, "revoke_token", fake_revoke)
    monkeypatch.setattr(auth_api, "refresh_access_token", fake_refresh)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/logout",
        "headers": [(b"authorization", b"Bearer access-token")],
    }
    await auth_api.logout(
        Request(scope),
        auth_api.RefreshRequest(refresh_token="refresh-token"),
    )
    assert revoked == {"access-token", "refresh-token"}

    with pytest.raises(HTTPException) as exc:
        await auth_api.refresh(
            auth_api.RefreshRequest(refresh_token="refresh-token")
        )
    assert exc.value.status_code == 401


# ============================================================
# 注册 / 登录 / 刷新 / 退出 契约测试
# ============================================================

class TestAuthContract:
    """测试注册、登录、刷新、退出的完整契约。"""

    # ---- Register ----

    @pytest.mark.asyncio
    async def test_register_valid(self):
        """有效注册应返回用户对象。"""
        from app.middleware.auth import register_user

        with patch("app.middleware.auth.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            # session.flush() 是 async 方法
            mock_session.flush = AsyncMock()
            # session.refresh() 是 async 方法
            mock_session.refresh = AsyncMock()
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value = mock_cm

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            user = await register_user("newuser", "password123")
            assert user is not None

    @pytest.mark.asyncio
    async def test_register_duplicate(self):
        """重复用户名应返回 None。"""
        from app.middleware.auth import register_user

        existing_user = MagicMock()
        with patch("app.middleware.auth.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value = mock_cm

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = existing_user
            mock_session.execute = AsyncMock(return_value=mock_result)

            user = await register_user("existing", "password123")
            assert user is None

    @pytest.mark.asyncio
    async def test_register_invalid_input(self):
        """无效输入应引发验证错误。"""
        from app.middleware.security import validate_input, SecurityValidationError

        # XSS 攻击特征应触发验证错误
        with pytest.raises(SecurityValidationError):
            validate_input('<script>alert("xss")</script>', "username", max_length=32)

        # SQL 注入特征应触发验证错误
        with pytest.raises(SecurityValidationError):
            validate_input("'; DROP TABLE users; --", "username", max_length=32)

    # ---- Login ----

    @pytest.mark.asyncio
    async def test_login_correct_credentials(self):
        """正确凭据应返回用户。"""
        from app.middleware.auth import authenticate_user

        mock_user = MagicMock()
        mock_user.is_active = True

        with patch("app.middleware.auth.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value = mock_cm

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("app.middleware.auth._verify_password", return_value=True):
                user = await authenticate_user("testuser", "correctpass")
                assert user is not None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """错误密码应返回 None。"""
        from app.middleware.auth import authenticate_user

        mock_user = MagicMock()
        mock_user.is_active = True

        with patch("app.middleware.auth.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value = mock_cm

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute = AsyncMock(return_value=mock_result)

            with patch("app.middleware.auth._verify_password", return_value=False):
                user = await authenticate_user("testuser", "wrongpass")
                assert user is None

    @pytest.mark.asyncio
    async def test_login_unknown_user(self):
        """未知用户应返回 None。"""
        from app.middleware.auth import authenticate_user

        with patch("app.middleware.auth.get_db_session") as mock_get_db:
            mock_session = MagicMock()
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_db.return_value = mock_cm

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            user = await authenticate_user("unknown", "password")
            assert user is None

    # ---- Refresh ----

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """无效 refresh token 应返回 None。"""
        from app.middleware.auth import refresh_access_token

        tokens = await refresh_access_token(
            "invalid-token",
            "test-secret-key",
            "HS256",
        )
        assert tokens is None

    # ---- Logout ----

    @pytest.mark.asyncio
    async def test_logout_revokes_tokens(self, monkeypatch):
        """退出登录应撤销 access token 和 refresh token。"""
        from app.api import auth as auth_api

        revoked = set()

        async def fake_revoke(token, *_args):
            revoked.add(token)
            return True

        monkeypatch.setattr(auth_api, "revoke_token", fake_revoke)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/logout",
            "headers": [(b"authorization", b"Bearer access-token")],
        }
        await auth_api.logout(
            Request(scope),
            auth_api.RefreshRequest(refresh_token="refresh-token"),
        )
        assert "access-token" in revoked
        assert "refresh-token" in revoked


# ============================================================
# 跨用户数据隔离测试
# ============================================================

class TestCrossUserDataIsolation:
    """测试用户 A 无法访问用户 B 的数据。"""

    @pytest.mark.asyncio
    async def test_user_a_cannot_access_user_b_error_book(self):
        """用户 A 无法获取用户 B 的错题本数据。"""
        from app.api import error_api

        class Item:
            def __init__(self, owner):
                self.owner = owner

            def to_dict(self):
                return {"owner": self.owner}

        class Manager:
            async def get_all(self, user_id):
                return [Item(user_id)]

        with patch.object(error_api, "get_error_book_manager", return_value=Manager()):
            result_a = await error_api.get_error_book(
                _request(SimpleNamespace(id="user-a", role="student"))
            )
            result_b = await error_api.get_error_book(
                _request(SimpleNamespace(id="user-b", role="student"))
            )

        # user-a 只能看到自己的数据
        assert all(item["owner"] == "user-a" for item in result_a)
        # user-b 只能看到自己的数据
        assert all(item["owner"] == "user-b" for item in result_b)
        # 互不包含对方的数据
        assert not any(item["owner"] == "user-b" for item in result_a)
        assert not any(item["owner"] == "user-a" for item in result_b)


# ============================================================
# 未认证访问保护资源测试
# ============================================================
# 由 test_unauthenticated_error_book 覆盖
