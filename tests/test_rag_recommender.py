"""
RAG 推荐引擎 + 工具层测试

覆盖：
1. LLMService 基础功能
2. VectorStoreManager 基础功能
3. RAGRecommender 降级策略
4. 工具层基础功能
5. DifficultyEstimator 集成
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import LLMService, LLMResponse
from app.services.vector_store import VectorStoreManager, VectorSearchResult
from app.services.rag_recommender import RAGRecommender, RecommendationRequest, RecommendationResult


@pytest.fixture
def mock_llm_service():
    service = MagicMock(spec=LLMService)
    service.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment":"测试","recommendation_reason":"测试","learning_advice":"测试","estimated_time_minutes":10}',
        model="qwen-max", provider="dashscope",
    ))
    return service


@pytest.fixture
def mock_vector_store():
    store = MagicMock(spec=VectorStoreManager)
    store.initialize = AsyncMock()
    store.hybrid_search = AsyncMock(return_value=[
        VectorSearchResult(id="v001", content="测试题", metadata={"category": "导数", "difficulty": 3}, score=0.85, distance=0.15),
    ])
    return store


# ── LLM Service ──

@pytest.mark.asyncio
async def test_llm_service_singleton():
    s1 = LLMService()
    s2 = LLMService()
    assert s1 is s2


@pytest.mark.asyncio
async def test_llm_service_cache_key():
    key = LLMService()._make_cache_key("hello", None, "qwen-max")
    assert len(key) == 32


def test_llm_response_serialization():
    r = LLMResponse("hello", "qwen-max", "dashscope", {"total_tokens": 10}, 100.0)
    d = r.to_dict()
    assert d["content"] == "hello"
    assert d["latency_ms"] == 100.0


# ── Vector Store ──

def test_clean_metadata():
    meta = {"name": "test", "count": 5, "rate": 0.85, "is_active": True, "tags": ["a", "b"], "nested": {"k": "v"}, "none_val": None}
    cleaned = VectorStoreManager._clean_metadata(meta)
    assert cleaned["name"] == "test"
    assert cleaned["count"] == 5
    assert isinstance(cleaned["tags"], str)
    assert "none_val" not in cleaned


def test_keyword_scores():
    store = VectorStoreManager()
    query = "导数 计算 f(x)"
    results = [
        VectorSearchResult("1", "求函数 f(x)=x² 的导数", {"category": "导数"}, 0.0, 0.0),
        VectorSearchResult("2", "三角函数 sin²x+cos²x", {"category": "三角函数"}, 0.0, 0.0),
    ]
    scores = store._calculate_keyword_scores(query, results)
    assert scores["1"] > scores["2"]


# ── RAG Recommender ──

@pytest.mark.asyncio
async def test_recommender_fallback():
    recommender = RAGRecommender()
    result = await recommender._get_fallback_recommendation(RecommendationRequest(user_id="test", target_category="导数", count=3))
    assert isinstance(result, RecommendationResult)
    assert result.meta.get("retrieval_method") == "fallback"


@pytest.mark.asyncio
async def test_question_to_dict():
    from app.data.models import Question
    q = Question(id="Q001", content="测试题", question_type="选择题", options=["A", "B"], answer="A", category="导数", difficulty=3)
    d = RAGRecommender._question_to_dict(q)
    assert d["id"] == "Q001"
    assert d["category"] == "导数"


# ── DifficultyEstimator ──

@pytest.mark.asyncio
async def test_score_to_difficulty():
    from app.services.difficulty_estimator import DifficultyEstimator
    assert DifficultyEstimator._score_to_difficulty(0.95) == 5
    assert DifficultyEstimator._score_to_difficulty(0.60) == 3
    assert DifficultyEstimator._score_to_difficulty(0.10) == 1


# ── Tool Layer ──

@pytest.mark.asyncio
async def test_recommend_tool_registration():
    from tools.recommend_tool import RecommendTool
    from tools.hybrid_registry import HybridToolRegistry
    registry = HybridToolRegistry()
    registry.register(RecommendTool())
    assert registry.has_tool("recommend_questions")


@pytest.mark.asyncio
async def test_skill_profile_tool_registration():
    from tools.skill_profile_tool import SkillProfileTool
    from tools.hybrid_registry import HybridToolRegistry
    registry = HybridToolRegistry()
    registry.register(SkillProfileTool())
    assert registry.has_tool("skill_profile")


@pytest.mark.asyncio
async def test_all_tools_registered():
    from tools import get_registry, _register_builtin_tools
    from app.config.settings import settings
    registry = get_registry()
    # 如果注册表为空（其他测试可能通过 init_registry(None) 重置了它），重新注册工具
    if registry.tool_count == 0:
        _register_builtin_tools(registry)
    expected = ["recommend_questions", "skill_profile", "explain_question", "search_questions", "error_book_analysis"]
    if settings.DASHSCOPE_API_KEY:
        expected.append("vision_tool")
    for name in expected:
        assert registry.has_tool(name), f"工具 {name} 未注册"