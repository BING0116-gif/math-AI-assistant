"""Tests for POST /api/recommend/session — the chat「练类似题」entry.

The endpoint chains: category inference (skipped when given) -> RAG recommender
-> practice session creation from the recommended IDs.
"""
import types

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.recommendation_api as recommendation_api
from app.api.recommendation_api import RecommendSessionRequest, recommend_and_create_session
from app.data.models import Base, Chapter, Course, KnowledgeGraphVersion, KnowledgePoint, Question, QuestionKnowledgePoint, User
from app.services.rag_recommender import RecommendationResult


class _FakeRecommender:
    def __init__(self, questions):
        self._questions = questions

    async def recommend(self, request):
        return RecommendationResult(
            questions=self._questions, ai_analysis={},
            meta={"target_category": request.target_category or "导数", "recommended_difficulty": 3},
        )


@pytest.mark.asyncio
async def test_recommend_session_creates_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        course = Course(id="course-1", code="calculus", name="高等数学", subject="math")
        version = KnowledgeGraphVersion(id="version-1", course_id="course-1", version="1.0", name="V1", status="published")
        chapter = Chapter(id="chapter-1", course_id="course-1", version_id="version-1", code="c1", name="函数")
        point = KnowledgePoint(id="point-1", course_id="course-1", version_id="version-1", chapter_id="chapter-1", code="limit", name="极限")
        user = User(id="user-1", username="student", email="student@example.test", password_hash="x")
        db.add_all([course, version, chapter, point, user])
        await db.flush()
        for index in range(2):
            question = Question(id=f"Q-{index}", content=f"题{index}", question_type="choice", options=[{"id": "A", "text": "2"}], answer="A", analysis="解析", category="导数", difficulty=2, course_id="course-1", version_id="version-1", review_status="published", grading_mode="deterministic", practice_eligible=True, answer_spec={"kind": "choice", "correct": "A"})
            db.add(question); await db.flush(); db.add(QuestionKnowledgePoint(question_id=question.id, knowledge_point_id="point-1"))
        await db.commit()

    async def fake_get():
        return _FakeRecommender([{"id": "Q-0", "content": "题0"}, {"id": "Q-1", "content": "题1"}])
    monkeypatch.setattr(recommendation_api, "get_rag_recommender", fake_get)

    response = await recommend_and_create_session(
        RecommendSessionRequest(category="导数", count=2),
        types.SimpleNamespace(state=types.SimpleNamespace(user_id="user-1")),
    )
    assert response["success"] is True
    assert response["data"]["session_id"]
    assert response["data"]["question_count"] == 2
    assert response["data"]["category"] == "导数"
    await engine.dispose()


@pytest.mark.asyncio
async def test_recommend_session_requires_auth(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await recommend_and_create_session(
            RecommendSessionRequest(category="导数"),
            types.SimpleNamespace(state=types.SimpleNamespace(user_id=None)),
        )
    assert exc.value.status_code == 401
