from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import admin_overview_api


def _request(user=None):
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/admin/overview",
        "headers": [],
        "state": {},
    })
    if user is not None:
        request.state.current_user = user
    return request


def test_overview_requires_admin():
    with pytest.raises(HTTPException) as exc:
        # The handler checks authorization before opening a database session.
        import asyncio
        asyncio.run(admin_overview_api.get_overview(_request(SimpleNamespace(role="student"))))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_overview_returns_only_aggregate_data(monkeypatch):
    class Result:
        def all(self):
            return [("published", 3), ("draft", 1)]

    class Session:
        def __init__(self):
            self.scalar = AsyncMock(side_effect=[10, 8, 1, 9, 20, 4])

        async def execute(self, _statement):
            return Result()

    class Context:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(admin_overview_api, "get_db_session", lambda: Context())
    body = await admin_overview_api.get_overview(
        _request(SimpleNamespace(role="admin", id="admin-1"))
    )

    assert body["code"] == 0
    assert body["data"]["users"] == {"total": 10, "active": 8, "students": 9, "admins": 1}
    assert body["data"]["question_bank"] == {"draft": 1, "reviewed": 0, "published": 3, "retired": 0}
    assert "messages" not in body["data"]
    assert "user_id" not in str(body["data"])
