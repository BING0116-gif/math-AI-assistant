"""Legacy student paper APIs remain explicit 410 compatibility endpoints."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.paper_student_api import generate_paper, get_paper, submit_paper


def _request():
    return SimpleNamespace(state=SimpleNamespace(user_id="student-1"))


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [
    lambda: generate_paper(_request(), {"config": {}}),
    lambda: get_paper(_request(), "old-paper"),
    lambda: submit_paper(_request(), "old-paper", {"answers": {}}),
])
async def test_legacy_student_paper_endpoints_return_410(call):
    with pytest.raises(HTTPException) as raised:
        await call()
    assert raised.value.status_code == 410
    assert raised.value.detail["code"] == "PAPER_API_DEPRECATED"
    assert raised.value.detail["replacement"] == "/api/practice/sessions"
