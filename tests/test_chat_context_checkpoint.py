import asyncio
import json
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, ChatContextCheckpoint, ChatMessage, ChatSession, OutboxEvent, User
from app.services.chat_context_checkpoint import _complete_prefix, _validate_summary
from app.services import chat_context_checkpoint as checkpoint_module
from app.services import llm_service
from app.config.settings import settings
from app.services.memory_application import MemoryApplicationService
from agent_core.token_budget import estimate_tokens
from app.services.chat_context_checkpoint import CHECKPOINT_CONTEXT_PREFIX
from app.api import chat_api


def test_complete_prefix_excludes_interleaved_unfinished_turn():
    def message(mid, role, turn, status=None):
        return ChatMessage(id=mid, role=role, content="test", metadata_={"turn_id": turn, **({"turn_status": status} if status else {})})

    rows = [message(1, "user", "a"), message(2, "user", "b"),
            message(3, "assistant", "b", "completed"), message(4, "assistant", "a", "completed"),
            message(5, "user", "c")]
    assert [row.id for row in _complete_prefix(rows)] == [1, 2, 3, 4]
    rows[3].metadata_["turn_status"] = "timeout"
    assert _complete_prefix(rows) == []


def test_summary_sources_must_be_in_user_session():
    value = {"topic": "极限", "active_problem": {"statement_ref": 1},
             "confirmed_facts": [{"text": "右极限", "source_message_ids": [1]}],
             "corrections": [], "open_questions": [], "learning_preference": None, "next_step": "检查定义域"}
    assert _validate_summary(value, {1}) == value
    try:
        _validate_summary(value, {2})
    except ValueError:
        pass
    else:
        raise AssertionError("cross-session source was accepted")


def test_checkpoint_queue_requires_owned_completed_assistant(tmp_path, monkeypatch):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkpoint.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([User(id="a", username="ctx-a", email="ctx-a@test.local", password_hash="x"),
                        User(id="b", username="ctx-b", email="ctx-b@test.local", password_hash="x")])
            await db.commit()
        service = MemoryApplicationService(factory)
        user_id = await service.append_message("a", "same", "user", "题目" + "x" * 1200, {"turn_id": "t"})
        assistant_id = await service.append_message("a", "same", "assistant", "答案" + "y" * 1200, {"turn_id": "t", "turn_status": "completed"})
        await service.append_message("b", "same", "user", "别人的题目", {"turn_id": "u"})
        assert not await service.queue_context_checkpoint("b", "same", assistant_id)
        assert not await service.queue_context_checkpoint("a", "same", user_id)
        assert not await service.queue_context_checkpoint("a", "same", assistant_id)
        monkeypatch.setattr(settings, "AGENT_CONTEXT_MAX_TOKENS", 256)
        assert await service.queue_context_checkpoint("a", "same", assistant_id)
        assert await service.queue_context_checkpoint("a", "same", assistant_id)
        assert await service.load_context_checkpoint("b", "same") is None
        monkeypatch.setattr(settings, "CHAT_CONTEXT_SHADOW_ENABLED", True)
        usage_a = await service.get_context_usage("a", "same")
        usage_b = await service.get_context_usage("b", "same")
        assert usage_a["used_tokens_estimated"] > 0
        assert usage_b["used_tokens_estimated"] > 0
        assert usage_a["is_estimate"] is True
        assert usage_a["compression_status"] == "queued"
        assert usage_b["compression_status"] == "idle"
        async with factory() as db:
            event = (await db.execute(select(OutboxEvent).where(OutboxEvent.user_id == "a"))).scalar_one()
            event.status = "processing"
            await db.commit()
        assert (await service.get_context_usage("a", "same"))["compression_status"] == "compressing"
        assert await service.get_context_usage("b", "a-only") is None
        await engine.dispose()
    asyncio.run(scenario())


def test_shadow_checkpoint_is_scoped_and_monotonic(tmp_path, monkeypatch):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'shadow.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(User(id="a", username="shadow-a", email="shadow-a@test.local", password_hash="x"))
            await db.commit()
        service = MemoryApplicationService(factory)
        ids = []
        for turn in range(3):
            ids.append(await service.append_message("a", "s", "user", "求极限，条件 x→0+。" + "x" * 400, {"turn_id": str(turn)}))
            ids.append(await service.append_message("a", "s", "assistant", "按右极限处理。" + "y" * 400,
                {"turn_id": str(turn), "turn_status": "completed"}))
        async with factory() as db:
            session_id = (await db.execute(select(ChatSession.id).where(ChatSession.user_id == "a"))).scalar_one()
        summary = {"topic": "极限", "active_problem": {"statement_ref": ids[0], "verbatim_constraints": ["x→0+"]},
            "confirmed_facts": [{"text": "右极限", "source_message_ids": [ids[0]]}],
            "corrections": [], "open_questions": [], "learning_preference": None, "next_step": "核查定义域"}
        class FakeLLM:
            async def generate_json(self, *args, **kwargs):
                return SimpleNamespace(parsed_json=summary, partial=False, model="fake")
        monkeypatch.setattr(checkpoint_module, "get_db_session", factory)
        monkeypatch.setattr(llm_service, "get_llm_service", lambda: FakeLLM())
        monkeypatch.setattr(settings, "CHAT_CONTEXT_SHADOW_ENABLED", True)
        monkeypatch.setattr(settings, "AGENT_CONTEXT_MAX_TOKENS", 256)
        assert await checkpoint_module.generate_checkpoint("a", session_id, ids[-1])
        assert await checkpoint_module.generate_checkpoint("a", session_id, ids[-1])
        assert not await checkpoint_module.generate_checkpoint("b", session_id, ids[-1])
        monkeypatch.setattr(settings, "CHAT_CONTEXT_INJECTION_ENABLED", True)
        for turn in range(3, 8):
            await service.append_message("a", "s", "user", "继续" + "x" * 200, {"turn_id": str(turn)})
            await service.append_message("a", "s", "assistant", "回答" + "y" * 200,
                {"turn_id": str(turn), "turn_status": "completed"})
        active = await service.load_context_checkpoint("a", "s")
        assert active is not None
        usage = await service.get_context_usage("a", "s")
        assert usage["used_tokens_estimated"] >= estimate_tokens(
            CHECKPOINT_CONTEXT_PREFIX + active["summary"], settings.LLM_MODEL)
        monkeypatch.setattr(settings, "CHAT_CONTEXT_MAX_REVISIONS", 1)
        assert await service.load_context_checkpoint("a", "s") is None
        async with factory() as db:
            row = (await db.execute(select(ChatContextCheckpoint))).scalar_one()
            assert row.user_id == "a"
            assert row.covered_through_message_id == ids[-1]
            assert row.revision == 1
        await engine.dispose()
    asyncio.run(scenario())


def test_legacy_session_is_not_queued_without_pairing_evidence(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(User(id="a", username="legacy-a", email="legacy-a@test.local", password_hash="x"))
            await db.commit()
        service = MemoryApplicationService(factory)
        await service.append_message("a", "old", "user", "旧题目")
        await service.append_message("a", "old", "assistant", "旧答案")
        await service.append_message("a", "old", "user", "新题目", {"turn_id": "new"})
        target = await service.append_message("a", "old", "assistant", "新答案",
            {"turn_id": "new", "turn_status": "completed"})
        assert not await service.queue_context_checkpoint("a", "old", target)
        await engine.dispose()
    asyncio.run(scenario())


def test_context_usage_route_requires_auth_and_returns_only_owned_session(monkeypatch):
    class FakeService:
        async def get_context_usage(self, user_id, session_id):
            assert user_id == "a"
            return {"used_tokens_estimated": 20, "budget_tokens": 4000,
                    "remaining_tokens_estimated": 3980, "is_estimate": True} if session_id == "owned" else None

    async def scenario():
        monkeypatch.setattr(chat_api, "_chat_memory_service", FakeService())
        request = Request({"type": "http", "headers": []})
        try:
            await chat_api.get_chat_context_usage("owned", request)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("unauthenticated request was accepted")
        request.state.user_id = "a"
        result = await chat_api.get_chat_context_usage("owned", request)
        assert result["data"]["remaining_tokens_estimated"] == 3980
        try:
            await chat_api.get_chat_context_usage("other", request)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("unowned session was accepted")

    asyncio.run(scenario())
