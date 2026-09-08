import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, User
from app.services.memory_application import MemoryApplicationService


def test_durable_chat_memory_is_user_scoped_and_deduplicated(tmp_path: Path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'memory.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([
                User(id="user-a", username="mem-a", email="mem-a@test.local", password_hash="x"),
                User(id="user-b", username="mem-b", email="mem-b@test.local", password_hash="x"),
            ])
            await db.commit()

        service = MemoryApplicationService(factory)
        text = "我喜欢先看直观例子，再学习严格证明。"
        await service.append_message("user-a", "default", "user", text)
        await service.append_message("user-a", "default", "assistant", "明白了。")
        await service.append_message("user-a", "default", "user", text)
        await service.append_message("user-b", "default", "user", "我喜欢直接看证明。")

        restored_a = await service.load_recent_messages("user-a", "default")
        restored_b = await service.load_recent_messages("user-b", "default")
        assert len(restored_a) == 3
        assert len(restored_b) == 1
        assert all("直接看证明" not in item["content"] for item in restored_a)

        memories_a = await service.retrieve("user-a", "例子 证明", "default")
        memories_b = await service.retrieve("user-b", "例子 证明", "default")
        assert len(memories_a) == 1  # repeated explicit statement is deduplicated
        assert memories_a[0]["content"].startswith("我喜欢先看直观例子")
        assert all("先看直观例子" not in item["content"] for item in memories_b)
        await engine.dispose()

    asyncio.run(scenario())


def test_memory_input_boundaries(tmp_path: Path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bounds.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        service = MemoryApplicationService(factory)
        for user_id, session_id in (("", "s"), ("u", ""), ("u", "x" * 129)):
            try:
                await service.load_recent_messages(user_id, session_id)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid scope must be rejected")
        await engine.dispose()

    asyncio.run(scenario())
