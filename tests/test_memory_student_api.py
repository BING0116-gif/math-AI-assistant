"""阶段四 6.5 用户可控记忆 API 回归测试(查看/确认/纠正/删除/导出+越权)。"""

import asyncio

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.api.memory_student_api import (
    confirm_memory,
    correct_memory,
    delete_memory,
    export_my_memories,
    list_my_memories,
    MemoryCorrectRequest,
)
from app.services.memory_store import MemoryStore


class _FakeRequest:
    def __init__(self, user_id):
        self.state = SimpleNamespace(user_id=user_id)


@pytest.fixture
def store(monkeypatch, tmp_path):
    """文件库 + 真实 MemoryStore(同步建表,异步会话指向同一文件)。"""
    import app.data.database as database
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.data.models import Base, User

    db_file = tmp_path / "mem_api.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    from app.data.models import Base as _Base
    _Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)

    async def _seed():
        async with factory() as db:
            db.add(User(id="owner", username="owner", email="o@e.test", password_hash="x"))
            db.add(User(id="other", username="other", email="o2@e.test", password_hash="x"))
            await db.commit()

    asyncio.run(_seed())

    store = MemoryStore()
    yield store
    asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_list_confirmed_corrected_and_export_flow(store, monkeypatch):
    monkeypatch.setattr("app.api.memory_student_api.get_memory_store", lambda: store)
    monkeypatch.setattr("app.api.memory_student_api.get_audit_logger", lambda: SimpleNamespace(
        log_modification=lambda *a, **k: None,
        log_deletion=lambda *a, **k: None,
        log_export=lambda *a, **k: None,
    ))

    memory_id = await store.create_error_memory(
        user_id="owner", question_id="q-1", question_content="求极限 lim(x→0) sinx/x",
        user_answer="0", correct_answer="1", error_type="calculation",
        high_category="高等数学", category="极限",
    )
    assert memory_id is not None

    # 列表:本人可见且 kind=misconception
    items = await list_my_memories(_FakeRequest("owner"), page=1, page_size=50)
    assert any(item["id"] == memory_id and item["memory_kind"] == "misconception" for item in items["data"])

    # 确认 → 置信度 0.9 + last_confirmed_at
    result = await confirm_memory(memory_id, _FakeRequest("owner"))
    assert result["data"]["confirmed"] is True
    refreshed = (await list_my_memories(_FakeRequest("owner"), page=1, page_size=50))["data"]
    row = next(item for item in refreshed if item["id"] == memory_id)
    assert row["confidence"] == 0.9 and row["last_confirmed_at"] is not None

    # 纠正 → 新记忆 0.95,旧记忆 superseded 链
    corrected = await correct_memory(memory_id, MemoryCorrectRequest(corrected_content="lim(x→0) sinx/x = 1,我曾误算为 0"), _FakeRequest("owner"))
    new_id = corrected["data"]["new_memory_id"]
    assert new_id and new_id != memory_id
    # 幂等:重复纠正返回同一新记忆
    again = await correct_memory(memory_id, MemoryCorrectRequest(corrected_content="再次纠正"), _FakeRequest("owner"))
    assert again["data"]["new_memory_id"] == new_id

    items = (await list_my_memories(_FakeRequest("owner"), page=1, page_size=50))["data"]
    old_row = next(item for item in items if item["id"] == memory_id)
    new_row = next(item for item in items if item["id"] == new_id)
    assert old_row["superseded_by"] == new_id and old_row["status"] == "archived"
    assert new_row["confidence"] == 0.95

    # 导出包含纠正链
    exported = await export_my_memories(_FakeRequest("owner"))
    exported_ids = {item["id"] for item in exported["data"]}
    assert {memory_id, new_id} <= exported_ids


@pytest.mark.asyncio
async def test_cross_user_access_is_rejected(store, monkeypatch):
    monkeypatch.setattr("app.api.memory_student_api.get_memory_store", lambda: store)
    monkeypatch.setattr("app.api.memory_student_api.get_audit_logger", lambda: SimpleNamespace(
        log_modification=lambda *a, **k: None,
        log_deletion=lambda *a, **k: None,
        log_export=lambda *a, **k: None,
    ))
    memory_id = await store.create_conversation_memory(user_id="owner", content="我偏好分步讲解")
    other_request = _FakeRequest("other")

    with pytest.raises(HTTPException) as e1:
        await confirm_memory(memory_id, other_request)
    assert e1.value.status_code == 404

    with pytest.raises(HTTPException) as e2:
        await correct_memory(memory_id, MemoryCorrectRequest(corrected_content="x"), other_request)
    assert e2.value.status_code == 404

    with pytest.raises(HTTPException) as e3:
        await delete_memory(memory_id, other_request)
    assert e3.value.status_code == 404

    # 越权列表/导出看不到他人记忆
    assert (await list_my_memories(other_request, page=1, page_size=50))["data"] == []
    assert (await export_my_memories(other_request))["data"] == []


@pytest.mark.asyncio
async def test_delete_is_owner_scoped_and_idempotent_404(store, monkeypatch):
    monkeypatch.setattr("app.api.memory_student_api.get_memory_store", lambda: store)
    monkeypatch.setattr("app.api.memory_student_api.get_audit_logger", lambda: SimpleNamespace(
        log_modification=lambda *a, **k: None,
        log_deletion=lambda *a, **k: None,
        log_export=lambda *a, **k: None,
    ))
    memory_id = await store.create_conversation_memory(user_id="owner", content="正在备考线性代数")

    result = await delete_memory(memory_id, _FakeRequest("owner"))
    assert result["data"]["deleted"] is True
    # 幂等:已删除后再次删除 → 404(与其他资源 404 口径一致)
    with pytest.raises(HTTPException):
        await delete_memory(memory_id, _FakeRequest("owner"))
