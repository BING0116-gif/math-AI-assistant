import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.data.models import (
    Base,
    Chapter,
    Course,
    ErrorItem,
    KnowledgeGraphVersion,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    User,
    VariantGeneration,
)
from app.services.question_dedup import find_similar_questions
from app.services.variant_generation import VariantGenerationError, create_variant_session


NUMERIC_BLUEPRINT = {
    "version": 1,
    "template": "function_value_numeric",
    "degree": 2,
    "variable": "x",
    "coefficient_range": [-5, 5],
    "input_range": [-3, 3],
    "variation_dimensions": ["coefficients", "input"],
}


class FakeEmbedding:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    async def encode_async(self, text):
        self.calls += 1
        if self.error:
            raise self.error
        return [0.1] * 512


class FakeVectorStore:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    async def semantic_search(self, vector, n_results=10, where=None):
        self.calls += 1
        assert len(vector) == 512
        return self.results[:n_results]


@pytest.mark.asyncio
async def test_high_similarity_result_is_rejected_and_logged(caplog):
    store = FakeVectorStore(
        [
            SimpleNamespace(id="Q-HIGH", score=0.97, metadata={}),
            SimpleNamespace(id="Q-LOW", score=0.81, metadata={}),
        ]
    )

    with caplog.at_level(logging.INFO, logger="app.services.question_dedup"):
        result = await find_similar_questions(
            FakeEmbedding(), store, "求函数在一点的导数", threshold=0.92
        )

    assert result == [{"question_id": "Q-HIGH", "score": 0.97}]
    assert "拦截高相似候选" in caplog.text


@pytest.mark.asyncio
async def test_configured_threshold_controls_filtering(monkeypatch):
    monkeypatch.setattr(settings, "QUESTION_DEDUP_THRESHOLD", 0.95)
    store = FakeVectorStore([SimpleNamespace(id="Q-BORDER", score=0.94)])

    assert await find_similar_questions(FakeEmbedding(), store, "边界题") == []


@pytest.mark.asyncio
async def test_embedding_failure_skips_dedup_with_warning(caplog):
    store = FakeVectorStore([])
    with caplog.at_level(logging.WARNING, logger="app.services.question_dedup"):
        result = await find_similar_questions(
            FakeEmbedding(RuntimeError("model offline")), store, "待生成题目"
        )

    assert result == []
    assert store.calls == 0
    assert "跳过向量查重" in caplog.text


def test_calibration_dataset_has_three_groups_with_twenty_pairs_each():
    path = Path("evaluations/question_dedup/v1/pairs.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload["groups"]) == {
        "same_rewrite",
        "same_concept_different",
        "cross_concept",
    }
    assert all(len(pairs) >= 20 for pairs in payload["groups"].values())
    assert all(
        len(pair) == 2 and all(isinstance(text, str) and text.strip() for text in pair)
        for pairs in payload["groups"].values()
        for pair in pairs
    )


async def _prepare_variant_database(monkeypatch, suffix: str):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database

    monkeypatch.setattr(database, "async_session_factory", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        course = Course(
            id=f"course-{suffix}", code=f"calculus-{suffix}", name="高等数学", subject="math"
        )
        version = KnowledgeGraphVersion(
            id=f"version-{suffix}",
            course_id=course.id,
            version="1.0",
            name="V1",
            status="published",
        )
        chapter = Chapter(
            id=f"chapter-{suffix}",
            course_id=course.id,
            version_id=version.id,
            code="c1",
            name="函数",
        )
        point = KnowledgePoint(
            id=f"point-{suffix}",
            course_id=course.id,
            version_id=version.id,
            chapter_id=chapter.id,
            code=f"function-value-{suffix}",
            name="函数值",
        )
        user = User(
            id=f"owner-{suffix}",
            username=f"owner-{suffix}",
            email=f"owner-{suffix}@example.test",
            password_hash="x",
        )
        db.add_all([course, version, chapter, point, user])
        await db.flush()
        source = Question(
            id=f"SOURCE-{suffix}",
            content="已知 f(x)=x^2，求 f(2)",
            question_type="numeric_fill",
            answer="4",
            answer_spec={"version": 1, "kind": "numeric_fill", "value": "4"},
            category="高数",
            course_id=course.id,
            version_id=version.id,
            review_status="published",
            is_active=True,
            grading_mode="deterministic",
            practice_eligible=True,
            exam_eligible=True,
            auto_grading_eligible=True,
            variant_blueprint=NUMERIC_BLUEPRINT,
        )
        db.add(source)
        await db.flush()
        db.add(
            QuestionKnowledgePoint(
                question_id=source.id, knowledge_point_id=point.id, is_primary=True
            )
        )
        db.add(
            ErrorItem(
                user_id=user.id,
                item_id=f"error-{suffix}",
                question=source.content,
                question_type="numeric_fill",
                question_id=source.id,
                source="attempt",
                knowledge_point_codes=[point.code],
            )
        )
        await db.commit()
    return engine, factory, user.id, f"error-{suffix}"


@pytest.mark.asyncio
async def test_variant_generation_retries_once_then_rejects_high_similarity(monkeypatch):
    engine, factory, user_id, error_id = await _prepare_variant_database(
        monkeypatch, "dedup"
    )
    store = FakeVectorStore([SimpleNamespace(id="Q-EXISTING", score=0.99)])
    embedding = FakeEmbedding()

    import app.services.variant_generation as variant_generation

    async def fake_get_vector_store():
        return store

    monkeypatch.setattr(variant_generation, "get_embedding_service", lambda: embedding)
    monkeypatch.setattr(variant_generation, "get_vector_store", fake_get_vector_store)

    with pytest.raises(VariantGenerationError) as caught:
        await create_variant_session(user_id, error_id, "idem-high")

    assert caught.value.code == "VARIANT_DUPLICATE_EXHAUSTED"
    assert store.calls == 2
    async with factory() as db:
        assert await db.scalar(select(VariantGeneration.id)) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_variant_generation_continues_when_embedding_is_unavailable(
    monkeypatch, caplog
):
    engine, factory, user_id, error_id = await _prepare_variant_database(
        monkeypatch, "degraded"
    )
    store = FakeVectorStore([])
    embedding = FakeEmbedding(RuntimeError("embedding unavailable"))

    import app.services.variant_generation as variant_generation

    async def fake_get_vector_store():
        return store

    monkeypatch.setattr(variant_generation, "get_embedding_service", lambda: embedding)
    monkeypatch.setattr(variant_generation, "get_vector_store", fake_get_vector_store)

    with caplog.at_level(logging.WARNING, logger="app.services.question_dedup"):
        result = await create_variant_session(user_id, error_id, "idem-degraded")

    assert result["status"] == "draft"
    assert "跳过向量查重" in caplog.text
    async with factory() as db:
        generation = await db.get(VariantGeneration, result["generation_id"])
        assert generation.validation_report["semantic_duplicate_matches"] == []
    await engine.dispose()
