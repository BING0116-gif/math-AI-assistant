from types import SimpleNamespace

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
