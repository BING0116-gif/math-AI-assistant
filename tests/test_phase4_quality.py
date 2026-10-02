import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.models import Base, Question
from app.services.rag_recommender import RAGRecommender
from app.services.vector_store import VectorSearchResult, VectorStoreManager
from content_quality_eval.phase4_practice import audit_phase4_practice
from rag_quality_eval.evaluator import evaluate_retrieval


ROOT = Path(__file__).resolve().parents[1]


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _question(question_id: str, **overrides):
    values = {
        "id": question_id,
        "content": question_id,
        "question_type": "choice",
        "options": [{"id": "A", "text": "正确"}, {"id": "B", "text": "错误"}],
        "answer": "A",
        "category": "导数",
        "difficulty": 3,
        "is_active": True,
        "review_status": "published",
        "practice_eligible": True,
    }
    values.update(overrides)
    return Question(**values)


def test_phase4_rag_gold_fixture_meets_offline_contract():
    gold = json.loads((ROOT / "evaluations/rag/v1/gold.json").read_text(encoding="utf-8"))
    run = json.loads((ROOT / "evaluations/rag/v1/offline_fixture_results.json").read_text(encoding="utf-8"))
    report = evaluate_retrieval(gold, run)
    assert report["status"] == "passed"
    assert report["metrics"]["recall_at_k"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["metrics"]["irrelevant_recall_rate"] == 0.0


def test_phase4_rag_eval_fails_closed_on_unpublished_or_user_metadata():
    gold = {
        "version": "test",
        "top_k": 5,
        "thresholds": {
            "min_recall_at_k": 0.0,
            "min_mrr": 0.0,
            "max_irrelevant_recall_rate": 1.0,
            "max_latency_p95_ms": 1000.0,
        },
        "cases": [{
            "case_id": "case-1", "kind": "unpublished", "expected_ids": [],
            "forbidden_ids": ["draft-1"],
        }],
    }
    run = {"results": [{
        "case_id": "case-1", "retrieved_ids": ["draft-1"], "latency_ms": 1,
        "metadata": {"user_id": "must-not-leak"},
    }]}
    report = evaluate_retrieval(gold, run)
    assert report["status"] == "failed"
    assert any("forbidden" in item for item in report["policy_failures"])
    assert any("sensitive_metadata" in item for item in report["policy_failures"])


def test_phase4_practice_bank_passes_machine_checks_and_requires_human_review():
    report = audit_phase4_practice()
    assert report["question_count"] == 195
    assert report["point_count"] == 39
    assert report["machine_checks"] == {"passed": True, "failures": []}
    assert report["status"] == "machine_passed_human_pending"
    assert report["human_review"]["required_count"] >= 39


def test_phase4_practice_review_gate_requires_accountable_complete_evidence():
    pending = audit_phase4_practice()
    reviews = {
        "reviewer": "math-reviewer-01",
        "questions": {
            question_id: {"decision": "approved", "note": "已核对题干、答案、解析和知识点映射"}
            for question_id in pending["human_review"]["missing_ids"]
        },
    }
    report = audit_phase4_practice(reviews)
    assert report["status"] == "approved"
    assert report["human_review"]["status"] == "complete"


@pytest.mark.asyncio
async def test_vector_backfill_only_accepts_published_active_eligible_questions(session_factory):
    rows = [
        _question("valid"),
        _question("draft", review_status="draft"),
        _question("inactive", is_active=False),
        _question("ineligible", practice_eligible=False),
    ]
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()

    recommender = RAGRecommender(db_session_factory=session_factory)
    final = []
    seen = set()
    await recommender._fetch_vector_questions([row.id for row in rows], final, seen)
    assert [row.id for row in final] == ["valid"]


@pytest.mark.asyncio
async def test_vector_failure_is_explicitly_degraded():
    store = MagicMock()
    store.hybrid_search = AsyncMock(side_effect=RuntimeError("qdrant down"))
    recommender = RAGRecommender(vector_store=store)
    results = await recommender._vector_retrieval("导数", 3, 5)
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_accepts_public_text_query_and_builds_embedding():
    store = VectorStoreManager()
    store.initialize = AsyncMock()
    store._embedding.encode_async = AsyncMock(return_value=[0.1, 0.2])
    store.semantic_search = AsyncMock(return_value=[
        VectorSearchResult(
            id="Q1", content="求函数的导数", metadata={"category": "导数"},
            score=0.9, distance=0.1,
        )
    ])

    results = await store.hybrid_search(query="", n_results=5)
    assert results == []  # 空查询短路,不触发编码与检索
    store._embedding.encode_async.assert_not_awaited()

    results = await store.hybrid_search(query="导数", n_results=5)

    store._embedding.encode_async.assert_awaited_with("导数")
    call = store.semantic_search.await_args.kwargs
    # 学生可见口径:仅检索已发布题目载荷
    assert call["where"]["content_kind"] == "question"
    assert call["where"]["review_status"] == "published"
    assert [row.id for row in results] == ["Q1"]
