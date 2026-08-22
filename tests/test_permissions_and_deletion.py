from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import recommendation_api
from app.config.settings import settings
from app.config.middleware_config import middleware_config
from app.middleware.path_matcher import PathMatcher
from app.data.models import (
    Base,
    ChatMessage,
    ChatSession,
    ErrorItem,
    ExamPaper,
    ExamSubmission,
    LearningRecord,
    Memory,
    MemoryAccessLog,
    MemoryTag,
    Question,
    User,
    UserProfile,
)
from app.security.access_control import require_internal_auth
from app.services.cache import CacheManager
from app.services.user_data_deletion import delete_user_data


def _request(user=None, headers=None):
    raw_headers = [
        (name.lower().encode(), value.encode())
        for name, value in (headers or {}).items()
    ]
    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": raw_headers}
    )
    if user:
        request.state.current_user = user
        request.state.user_id = user.id
    return request


@pytest.mark.asyncio
async def test_question_import_requires_admin():
    body = recommendation_api.ImportQuestionsRequest(questions=[])

    with pytest.raises(HTTPException) as exc:
        await recommendation_api.import_questions(
            body, _request(SimpleNamespace(id="student", role="student"))
        )
    assert exc.value.status_code == 403


def test_recommendation_identity_has_no_token_fallback():
    request = _request(headers={"Authorization": "Bearer forged-or-stale-token"})
    assert recommendation_api._get_user_id(request) is None


def test_internal_auth_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "QUESTION_SYSTEM_API_KEY", "")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(_request())
    assert exc.value.status_code == 503

    monkeypatch.setattr(settings, "QUESTION_SYSTEM_API_KEY", "secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_auth(_request(headers={"X-API-Key": "wrong"}))
    assert exc.value.status_code == 403
    require_internal_auth(_request(headers={"X-API-Key": "secret"}))


def test_internal_routes_bypass_bearer_only_for_route_level_key_auth():
    assert "/api/internal/" in middleware_config.NO_AUTH_PATHS
    matcher = PathMatcher(skip_paths=list(middleware_config.NO_AUTH_PATHS))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/internal/event/question-finish",
            "headers": [],
        }
    )
    assert matcher.should_skip_auth(request)


@pytest.mark.asyncio
async def test_delete_user_data_is_complete_and_isolated():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        session.add_all(
            [
                User(
                    id="user-a",
                    username="a",
                    email="a@example.com",
                    password_hash="hash",
                ),
                User(
                    id="user-b",
                    username="b",
                    email="b@example.com",
                    password_hash="hash",
                ),
                Question(
                    id="q1",
                    content="1+1",
                    question_type="short",
                    answer="2",
                    category="math",
                ),
            ]
        )
        await session.flush()

        record = LearningRecord(
            user_id="user-a",
            question_id="q1",
            event_type="answer",
            question_content="1+1",
            category="math",
        )
        other_record = LearningRecord(
            user_id="user-b",
            question_id="q1",
            event_type="answer",
            question_content="1+1",
            category="math",
        )
        chat = ChatSession(id="chat-a", user_id="user-a")
        paper = ExamPaper(
            id="paper-a", user_id="user-a", config={}, question_ids=["q1"]
        )
        memory = Memory(
            user_id="user-a",
            content="memory",
            embedding_summary="summary",
            expire_at=1,
            created_at=1,
        )
        session.add_all(
            [
                record,
                other_record,
                chat,
                ChatMessage(session=chat, role="user", content="hello"),
                paper,
                ExamSubmission(paper=paper, question_id="q1"),
                ErrorItem(user_id="user-a", item_id="e1", question="wrong"),
                memory,
                UserProfile(
                    user_id="user-a",
                    summary_text="summary",
                    full_profile_json="{}",
                    updated_at=1,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                MemoryTag(memory_id=memory.id, tag_name="tag"),
                MemoryAccessLog(
                    memory_id=memory.id,
                    user_id="user-a",
                    session_id="chat-a",
                    accessed_at=1,
                ),
            ]
        )
        await session.commit()

        counts = await delete_user_data(session, "user-a")
        await session.commit()

        assert sum(counts.values()) == 10
        for model in (
            LearningRecord,
            ChatSession,
            ChatMessage,
            ExamPaper,
            ExamSubmission,
            ErrorItem,
            Memory,
            MemoryTag,
            MemoryAccessLog,
            UserProfile,
        ):
            remaining = await session.scalar(select(func.count()).select_from(model))
            expected = 1 if model is LearningRecord else 0
            assert remaining == expected
        assert await session.get(User, "user-a") is not None
        assert await session.get(User, "user-b") is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_cache_invalidation_matches_real_key_shapes():
    cache = CacheManager()
    cache.l1_cache = {
        "profile:user-a": {},
        "user:user-a:stats": {},
        "profile:user-b": {},
    }
    await cache.invalidate_user("user-a")
    assert cache.l1_cache == {"profile:user-b": {}}
