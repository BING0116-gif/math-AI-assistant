"""阶段四 6.4 注入侧防护回归测试:misconception 纠正框架/context 时间标注/review 排除。"""

import pytest

from agent_core.agent import build_memory_context_lines


def test_misconception_memory_is_injected_with_correction_frame():
    lines = build_memory_context_lines([
        {"memory_kind": "misconception", "content": "我曾认为 sinx/x 在 0 处等于 0"},
    ])
    assert any("该生曾犯的错" in line and "不可采纳" in line for line in lines)
    # 纠正框架不可缺:防历史错误被当作正确知识注入
    assert any("sinx/x" in line for line in lines)


def test_context_memory_carries_time_annotation():
    import time as time_module

    three_days_ago = int(time_module.time()) - 3 * 86400
    lines = build_memory_context_lines([
        {"memory_kind": "context", "content": "正在备考线性代数", "created_at": three_days_ago},
        {"memory_kind": "context", "content": "无时间戳记忆"},
    ])
    assert any("3 天前的会话" in line for line in lines)
    assert any("往期会话" in line and "无时间戳记忆" in line for line in lines)


def test_preference_and_fact_pass_through_with_global_disclaimer():
    lines = build_memory_context_lines([
        {"memory_kind": "preference", "content": "偏好分步讲解"},
        {"memory_kind": "fact", "content": "已完成高数上册"},
    ])
    assert lines[0].startswith("【相关长期记忆】")
    assert any("- 偏好分步讲解" == line for line in lines[1:])
    assert any("- 已完成高数上册" == line for line in lines[1:])


def test_missing_kind_defaults_to_context_safe_path():
    lines = build_memory_context_lines([{"content": "旧数据缺 kind"}])
    assert any("往期会话" in line for line in lines)


def test_empty_and_none_memories_produce_disclaimer_only():
    assert build_memory_context_lines([]) == [pytest.approx(build_memory_context_lines(None)[0])]
    assert len(build_memory_context_lines(None)) == 1


@pytest.mark.asyncio
async def test_retrieve_excludes_unresolved_review_conflicts(tmp_path, monkeypatch):
    """conflict_status=review 的双侧记忆不得注入(6.4 注入防护)。"""
    import app.data.database as database
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.data.models import Base, Memory, User
    from app.services.memory_application import MemoryApplicationService

    db_file = tmp_path / "inject.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)

    async with factory() as db:
        db.add(User(id="inject-user", username="iu", email="iu@e.test", password_hash="x"))
        now = int(__import__("time").time())
        db.add(Memory(
            user_id="inject-user", memory_type="profile", content="用户来自四川",
            embedding_summary="用户来自四川", importance=0.9, status="active",
            expire_at=now + 86400, memory_strength=0.9, created_at=now,
            memory_kind="fact", confidence=0.6, conflict_status="review",
        ))
        db.add(Memory(
            user_id="inject-user", memory_type="profile", content="用户来自云南",
            embedding_summary="用户来自云南", importance=0.9, status="active",
            expire_at=now + 86400, memory_strength=0.9, created_at=now + 1,
            memory_kind="fact", confidence=0.6, conflict_status="review",
        ))
        db.add(Memory(
            user_id="inject-user", memory_type="conversation", content="已完成高数上册",
            embedding_summary="已完成高数上册", importance=0.8, status="active",
            expire_at=now + 86400, memory_strength=0.9, created_at=now + 2,
            memory_kind="fact", confidence=0.6, conflict_status="none",
        ))
        await db.commit()

    service = MemoryApplicationService(session_factory=factory)
    results = await service.retrieve("inject-user", "高数 已完成", "session-inject", limit=5)
    contents = [item["content"] for item in results]
    assert any("已完成高数上册" in content for content in contents)
    assert not any("四川" in content or "云南" in content for content in contents), \
        "review 冲突双侧记忆都不得注入"
    kinds = {item["memory_kind"] for item in results}
    assert "fact" in kinds
    await engine.dispose()
