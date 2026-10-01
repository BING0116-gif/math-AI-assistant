from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api import memory_dashboard


def _admin_request() -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.current_user = SimpleNamespace(role="admin")
    return request


@pytest.mark.asyncio
async def test_dashboard_user_escapes_path_profile_and_memory_content(monkeypatch):
    attack = '<img src=x onerror="alert(1)">'

    class Store:
        async def get_user_memories(self, *, user_id, limit):
            assert user_id == attack
            assert limit == 50
            return ([{
                "id": attack,
                "memory_type": attack,
                "high_category": attack,
                "category": attack,
                "embedding_summary": attack,
                "importance": 1,
                "memory_strength": 2,
                "status": attack,
            }], 1)

    class ProfileService:
        async def get_profile(self, user_id):
            assert user_id == attack
            return {"summary_text": attack}

    monkeypatch.setattr(memory_dashboard, "get_memory_store", lambda: Store())
    monkeypatch.setattr(memory_dashboard, "get_profile_service", lambda: ProfileService())

    response = await memory_dashboard.dashboard_user(_admin_request(), attack)
    page = response.body.decode()

    assert attack not in page
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in page
    assert 'class="type-badge type-unknown"' in page
    assert 'style="width: 100%;"' in page


def test_render_user_memories_handles_malformed_numeric_values_safely():
    page = memory_dashboard._render_user_memories([{
        "memory_type": 'x\" onclick=\"alert(1)',
        "memory_strength": "not-a-number",
        "importance": "not-a-number",
        "embedding_summary": None,
    }])

    assert 'onclick="alert(1)' not in page
    assert "x&#34; onclick=&#34;alert(1)" in page
    assert 'class="type-badge type-unknown"' in page
    assert 'style="width: 0%;"' in page
    assert "重要度: 0.0" in page


@pytest.mark.asyncio
async def test_dashboard_stats_autoescapes_template_data(monkeypatch):
    attack = '<svg onload="alert(1)">'

    monkeypatch.setattr(memory_dashboard, "get_memory_store", lambda: object())

    async def stats(_store):
        return {
            "total_memories": 1,
            "active_users": 1,
            "error_count": 0,
            "conversation_count": 0,
            "milestone_count": 0,
            "archived_count": 0,
        }

    async def memories():
        return ([{
            "id": attack,
            "user_id": attack,
            "memory_type": attack,
            "type_class": "type-unknown",
            "high_category": attack,
            "category": attack,
            "summary": attack,
            "strength_pct": 0,
            "status": attack,
        }], False)

    async def profiles():
        return ([{"user_id": attack, "version": attack, "summary": attack}], False)

    monkeypatch.setattr(memory_dashboard, "_get_system_stats", stats)
    monkeypatch.setattr(memory_dashboard, "_get_recent_memories", memories)
    monkeypatch.setattr(memory_dashboard, "_get_user_profiles", profiles)

    response = await memory_dashboard.dashboard_stats(_admin_request())
    page = response.body.decode()

    assert attack not in page
    assert "&lt;svg onload=&#34;alert(1)&#34;&gt;" in page
    assert "onclick=" not in page
