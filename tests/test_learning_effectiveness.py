from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import admin_learning_effectiveness_api
from app.services.learning_effectiveness import EVENT_CONTRACT


def _request(role="student"):
    request = Request({"type": "http", "method": "GET", "path": "/api/admin/learning-effectiveness", "headers": [], "state": {}})
    request.state.current_user = SimpleNamespace(role=role)
    return request


def test_event_contract_is_explicit_and_privacy_safe():
    assert {"activity", "practice", "review", "ai_feedback", "mastery"} <= EVENT_CONTRACT.keys()
    assert all("user_id" in spec["fields"] and "aggregate" in spec["privacy"] for spec in EVENT_CONTRACT.values())


@pytest.mark.asyncio
async def test_report_requires_admin():
    with pytest.raises(HTTPException) as exc:
        await admin_learning_effectiveness_api.learning_effectiveness(_request())
    assert exc.value.status_code == 403
