"""阶段四 6.1/6.2/6.3 记忆 kind 类型系统与置信度引擎回归测试。"""

import pytest

from app.services.memory_policy import (
    CONFIDENCE_AUTO_EXTRACTED,
    MEMORY_KIND_CONTEXT,
    MEMORY_KIND_FACT,
    MEMORY_KIND_MISCONCEPTION,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_PROFILE,
    infer_memory_kind,
)


def test_kind_inference_heuristic():
    assert infer_memory_kind(MEMORY_TYPE_ERROR) == MEMORY_KIND_MISCONCEPTION
    assert infer_memory_kind(MEMORY_TYPE_PROFILE) == MEMORY_KIND_FACT
    assert infer_memory_kind(MEMORY_TYPE_CONVERSATION) == MEMORY_KIND_CONTEXT
    # 未知类型保守落 context(不注入推导)
    assert infer_memory_kind("unknown-type") == MEMORY_KIND_CONTEXT


def test_kind_inference_explicit_and_invalid():
    assert infer_memory_kind(MEMORY_TYPE_CONVERSATION, MEMORY_KIND_FACT) == MEMORY_KIND_FACT
    with pytest.raises(ValueError):
        infer_memory_kind(MEMORY_TYPE_ERROR, "not-a-kind")


def test_create_paths_assign_kind_and_initial_confidence():
    """写入路径强制 kind;自动提取初始置信度 0.5(6.3)。"""
    from app.services.memory_policy import MEMORY_INIT_STRENGTH

    # 通过 policy 契约验证:所有 memory_type 都能推出合法 kind
    for memory_type in MEMORY_INIT_STRENGTH:
        kind = infer_memory_kind(memory_type)
        assert kind in {"preference", "fact", "misconception", "context"}
    assert CONFIDENCE_AUTO_EXTRACTED == 0.5


def test_migration_head_includes_memory_columns():
    """新迁移在 head 且模型列齐备(空库升级在 test_content_ai 全链验证)。"""
    from app.data.models import Memory

    for column in ("confidence", "memory_kind", "last_confirmed_at", "superseded_by", "conflict_status"):
        assert hasattr(Memory, column), f"Memory 缺少列 {column}"


def test_low_confidence_archive_threshold_is_doc_value():
    from app.services.memory_policy import CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD

    assert CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD == 0.15


def test_conversation_kind_classifier_routes_style_and_progress():
    """6.6:风格/偏好表述 → preference,课程/进度陈述 → fact,其余 context。"""
    from app.services.memory_policy import infer_conversation_kind

    assert infer_conversation_kind("请分步讲解，不要直接给答案") == "preference"
    assert infer_conversation_kind("我喜欢多举例子、打个比方的讲法") == "preference"
    assert infer_conversation_kind("我已经学完高数上册，正在备考线代") == "fact"
    assert infer_conversation_kind("今天做错了一道极限题") == "context"


@pytest.mark.asyncio
async def test_create_conversation_memory_auto_classifies_kind(tmp_path, monkeypatch):
    import app.data.database as database
    from sqlalchemy import create_engine, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.data.models import Base, Memory, User
    from app.services.memory_store import MemoryStore

    db_file = tmp_path / "kind.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session_factory", factory)

    async with factory() as db:
        db.add(User(id="kind-user", username="ku", email="ku@e.test", password_hash="x"))
        await db.commit()

    store = MemoryStore()
    pref_id = await store.create_conversation_memory(user_id="kind-user", content="请以后分步讲解，不要直接给答案")
    fact_id = await store.create_conversation_memory(user_id="kind-user", content="我已经学完高数上册")
    ctx_id = await store.create_conversation_memory(user_id="kind-user", content="今天讨论了一道极限题")

    async with factory() as db:
        rows = {row.id: row for row in (await db.execute(select(Memory).where(Memory.user_id == "kind-user"))).scalars()}
    assert rows[pref_id].memory_kind == "preference"
    assert rows[fact_id].memory_kind == "fact"
    assert rows[ctx_id].memory_kind == "context"
    await engine.dispose()
