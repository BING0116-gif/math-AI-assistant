"""
RAG 核心服务模块综合测试 — 覆盖 question_importer, vector_store, llm_service, rag_recommender。

目标覆盖率：各模块 ≥ 80%
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import json
import os
import tempfile
import time

import pandas as pd

from app.services.llm_service import (
    LLMService, LLMResponse, LLMProvider, get_llm_service,
)
from app.services.vector_store import (
    VectorStoreManager, VectorSearchResult, get_vector_store,
)
from app.services.question_importer import (
    QuestionImporter, ImportResult,
)
from app.services.rag_recommender import (
    RAGRecommender, RecommendationRequest, RecommendationResult, get_rag_recommender,
)
from tools.base_tool import ToolInput, ToolOutput, ToolCapability, BaseTool


# ═══════════════════════════════════════════════════════════════
# LLMService 测试
# ═══════════════════════════════════════════════════════════════

class TestLLMServiceCache:
    """LLM 缓存机制测试"""

    def test_get_from_cache(self):
        svc = LLMService()
        svc._cache_ttl = 300
        key = "test_key_unique"
        resp = LLMResponse("cached content", "qwen-max", "dashscope")
        svc._cache[key] = (resp, time.time())
        result = svc._get_from_cache(key)
        assert result is not None
        assert result.content == "cached content"
        assert result.cached is True

    def test_cache_expired(self):
        svc = LLMService()
        svc._cache_ttl = 1
        key = "expired_key_unique"
        resp = LLMResponse("expired", "qwen-max", "dashscope")
        svc._cache[key] = (resp, time.time() - 10)
        result = svc._get_from_cache(key)
        assert result is None

    def test_add_to_cache(self):
        svc = LLMService()
        svc._cache_max_size = 100
        resp = LLMResponse("test content" * 10, "qwen-max", "dashscope")
        svc._add_to_cache("k1_unique", resp)
        assert "k1_unique" in svc._cache

    def test_add_to_cache_short_content_skipped(self):
        svc = LLMService()
        svc._cache_max_size = 100
        resp = LLMResponse("short", "qwen-max", "dashscope")
        svc._add_to_cache("k1_short", resp)
        assert "k1_short" not in svc._cache

    def test_add_to_cache_eviction(self):
        svc = LLMService()
        svc._cache_max_size = 3
        keys = []
        for i in range(5):
            resp = LLMResponse(f"content {i}" * 10, "qwen-max", "dashscope")
            key = f"key_evict_{i}"
            keys.append(key)
            svc._add_to_cache(key, resp)
        assert len(svc._cache) <= 3

    def test_clear_cache(self):
        svc = LLMService()
        resp = LLMResponse("content" * 10, "m", "p")
        svc._cache["clear_test_key"] = (resp, time.time())
        count = svc.clear_cache()
        assert count >= 1
        assert len(svc._cache) == 0

    def test_get_cache_stats(self):
        svc = LLMService()
        resp = LLMResponse("content" * 10, "m", "p")
        svc._cache["stats_test_key"] = (resp, time.time())
        stats = svc.get_cache_stats()
        assert stats["cache_size"] >= 1
        assert isinstance(stats["ttl_seconds"], int)
        assert stats["ttl_seconds"] > 0
        # Cleanup
        del svc._cache["stats_test_key"]


class TestLLMServiceCore:
    """LLM 核心功能测试"""

    def test_singleton(self):
        s1 = LLMService()
        s2 = LLMService()
        assert s1 is s2

    def test_get_llm_service_factory(self):
        svc = get_llm_service()
        assert isinstance(svc, LLMService)

    def test_build_messages_with_system(self):
        svc = LLMService()
        msgs = svc._build_messages("hello", "be helpful")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "be helpful"
        assert msgs[1]["role"] == "user"

    def test_build_messages_no_system(self):
        svc = LLMService()
        msgs = svc._build_messages("hello")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_make_cache_key_deterministic(self):
        svc = LLMService()
        k1 = svc._make_cache_key("prompt", "system", "qwen-max")
        k2 = svc._make_cache_key("prompt", "system", "qwen-max")
        assert k1 == k2
        assert len(k1) == 32

    def test_make_cache_key_different(self):
        svc = LLMService()
        k1 = svc._make_cache_key("p1", "s", "m")
        k2 = svc._make_cache_key("p2", "s", "m")
        assert k1 != k2


class TestLLMResponseSerialization:
    """LLMResponse 序列化测试"""

    def test_to_dict_full(self):
        r = LLMResponse("hello", "qwen-max", "dashscope", {"total_tokens": 10}, 100.0, True)
        d = r.to_dict()
        assert d["content"] == "hello"
        assert d["model"] == "qwen-max"
        assert d["provider"] == "dashscope"
        assert d["usage"]["total_tokens"] == 10
        assert d["latency_ms"] == 100.0
        assert d["cached"] is True

    def test_to_dict_minimal(self):
        r = LLMResponse("hi", "gpt-4", "openai")
        d = r.to_dict()
        assert d["content"] == "hi"
        assert d["usage"] == {}
        assert d["latency_ms"] == 0.0
        assert d["cached"] is False


class TestLLMServiceAnalyze:
    """LLM 题目难度分析测试"""

    @pytest.mark.asyncio
    async def test_analyze_question_difficulty_json(self):
        svc = get_llm_service()
        mock_resp = MagicMock()
        mock_resp.content = '{"estimated_difficulty": 4, "reason": "复杂", "knowledge_points": ["导数", "链式法则"]}'

        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_resp
            result = await svc.analyze_question_difficulty("求导", "导数")
            assert result["estimated_difficulty"] == 4
            assert "导数" in result["knowledge_points"]

    @pytest.mark.asyncio
    async def test_analyze_question_difficulty_json_with_markdown(self):
        svc = get_llm_service()
        mock_resp = MagicMock()
        mock_resp.content = '```json\n{"estimated_difficulty": 3, "reason": "标准", "knowledge_points": ["极限"]}\n```'

        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_resp
            result = await svc.analyze_question_difficulty("求极限", "极限")
            assert result["estimated_difficulty"] == 3

    @pytest.mark.asyncio
    async def test_analyze_question_difficulty_code_block(self):
        svc = get_llm_service()
        mock_resp = MagicMock()
        mock_resp.content = '```\n{"estimated_difficulty": 2, "reason": "基础", "knowledge_points": ["集合"]}\n```'

        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_resp
            result = await svc.analyze_question_difficulty("集合题", "集合")
            assert result["estimated_difficulty"] == 2

    @pytest.mark.asyncio
    async def test_analyze_question_difficulty_fallback(self):
        svc = get_llm_service()
        mock_resp = MagicMock()
        mock_resp.content = "invalid json response"

        with patch.object(svc, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_resp
            result = await svc.analyze_question_difficulty("题目", "数学")
            assert result["estimated_difficulty"] == 3
            assert result["reason"] == "AI分析失败"


class TestLLMServiceGenerate:
    """LLM 生成测试"""

    @pytest.mark.asyncio
    async def test_generate_no_cache(self):
        svc = get_llm_service()
        mock_choice = MagicMock()
        mock_choice.message.content = "generated text"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "qwen-max"
        mock_resp.usage = None
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate("hello", use_cache=False)
            assert result.content == "generated text"
            assert result.model == "qwen-max"

    @pytest.mark.asyncio
    async def test_generate_with_cache(self):
        svc = get_llm_service()
        resp = LLMResponse("cached", "qwen-max", "dashscope")
        cache_key = svc._make_cache_key("prompt_cache_test", None, "qwen-max")
        svc._cache[cache_key] = (resp, time.time())

        result = await svc.generate("prompt_cache_test", use_cache=True)
        assert result.content == "cached"
        assert result.cached is True

    @pytest.mark.asyncio
    async def test_generate_with_math_model(self):
        svc = get_llm_service()
        mock_choice = MagicMock()
        mock_choice.message.content = "math result"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "qwen-turbo"
        mock_resp.usage = None
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate_with_math_model("math problem", use_tir=True)
            assert result.content == "math result"
            call_args = mock_client.chat.completions.create.call_args
            assert "TIR" in call_args[1]["messages"][-1]["content"]

    @pytest.mark.asyncio
    async def test_generate_with_math_model_no_tir(self):
        svc = get_llm_service()
        mock_choice = MagicMock()
        mock_choice.message.content = "no tir"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.model = "qwen-turbo"
        mock_resp.usage = None
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch.object(svc, '_client', mock_client):
            result = await svc.generate_with_math_model("math", use_tir=False)
            assert result.content == "no tir"

    @pytest.mark.asyncio
    async def test_generate_error(self):
        svc = get_llm_service()
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with patch.object(svc, '_client', mock_client):
            with pytest.raises(Exception, match="API error"):
                await svc.generate("prompt", use_cache=False)


# ═══════════════════════════════════════════════════════════════
# VectorStoreManager 测试
# ═══════════════════════════════════════════════════════════════

class TestVectorStoreMetadata:
    """元数据清理测试"""

    def test_clean_metadata_all_types(self):
        meta = {
            "str_val": "hello",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "list_val": [1, 2, 3],
            "dict_val": {"a": 1},
            "none_val": None,
            "complex_val": complex(1, 2),
        }
        cleaned = VectorStoreManager._clean_metadata(meta)
        assert cleaned["str_val"] == "hello"
        assert cleaned["int_val"] == 42
        assert cleaned["float_val"] == 3.14
        assert cleaned["bool_val"] is True
        assert isinstance(cleaned["list_val"], str)
        assert isinstance(cleaned["dict_val"], str)
        assert "none_val" not in cleaned
        assert isinstance(cleaned["complex_val"], str)

    def test_clean_metadata_empty(self):
        assert VectorStoreManager._clean_metadata({}) == {}


class TestVectorStoreKeywordScores:
    """关键词评分测试"""

    def test_chinese_keywords(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        query = "导数 求导 f(x)"
        results = [
            VectorSearchResult("1", "求函数 f(x)=x² 的导数", {"category": "导数"}, 0.0, 0.0),
            VectorSearchResult("2", "三角函数 sin²x+cos²x", {"category": "三角函数"}, 0.0, 0.0),
        ]
        scores = store._calculate_keyword_scores(query, results)
        assert scores["1"] > scores["2"]

    def test_empty_query(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        results = [
            VectorSearchResult("1", "test", {}, 0.0, 0.0),
        ]
        scores = store._calculate_keyword_scores("", results)
        assert scores == {}

    def test_keyword_in_metadata(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        query = "导数"
        results = [
            VectorSearchResult("1", "some content", {"category": "导数"}, 0.0, 0.0),
        ]
        scores = store._calculate_keyword_scores(query, results)
        assert scores["1"] > 0


class TestVectorStoreFormat:
    """结果格式化测试"""

    def test_format_results_empty(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        results = store._format_results(None)
        assert results == []

    def test_format_results_no_ids(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        results = store._format_results({"ids": [], "documents": None, "metadatas": None, "distances": None})
        assert results == []

    def test_format_results_valid(self):
        store = VectorStoreManager(persist_directory="./test_chroma")
        raw = {
            "ids": [["Q1", "Q2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"cat": "导数"}, {"cat": "极限"}]],
            "distances": [[0.1, 0.2]],
        }
        results = store._format_results(raw)
        assert len(results) == 2
        assert results[0].id == "Q1"
        assert results[0].content == "doc1"
        assert results[0].score == pytest.approx(0.9)
        assert results[0].distance == 0.1
        assert results[1].id == "Q2"


class TestVectorStoreSingleton:
    """向量存储单例测试"""

    @pytest.mark.asyncio
    async def test_get_vector_store_singleton(self):
        with patch('app.services.vector_store.VectorStoreManager.initialize', new_callable=AsyncMock):
            vs1 = await get_vector_store()
            vs2 = await get_vector_store()
            assert vs1 is vs2


# ═══════════════════════════════════════════════════════════════
# QuestionImporter 测试
# ═══════════════════════════════════════════════════════════════

class TestQuestionImporterDataFrame:
    """DataFrame 导入测试"""

    @pytest.mark.asyncio
    async def test_import_missing_required_columns(self):
        importer = QuestionImporter()
        df = pd.DataFrame([{"content": "test", "category": "math"}])
        result = await importer._import_dataframe(df)
        assert result.total == 0
        assert len(result.errors) > 0
        assert "缺少必需列" in result.errors[0]

    @pytest.mark.asyncio
    async def test_import_empty_id(self):
        importer = QuestionImporter()
        df = pd.DataFrame([{
            "id": "", "content": "test", "category": "math", "answer": "A",
        }])
        result = await importer._import_dataframe(df)
        assert result.failed == 1
        assert result.success == 0


class TestQuestionImporterBuild:
    """Question 数据构建测试"""

    def test_build_question_data_basic(self):
        importer = QuestionImporter()
        row = pd.Series({
            "id": "Q001", "content": "测试题", "question_type": "选择题",
            "options": '["A", "B", "C"]', "answer": "A", "analysis": "解析内容",
            "category": "导数", "sub_categories": "基础", "knowledge_points": '["求导"]',
            "difficulty": 3, "source": "教材", "estimated_time": 5,
        })
        q = importer._build_question_data(row)
        assert q.id == "Q001"
        assert q.content == "测试题"
        assert q.options == ["A", "B", "C"]
        assert q.difficulty == 3
        assert q.is_active is True

    def test_build_question_data_string_options(self):
        importer = QuestionImporter()
        row = pd.Series({
            "id": "Q002", "content": "test", "question_type": "text",
            "options": "not json", "answer": "B", "analysis": "",
            "category": "数学", "sub_categories": "", "knowledge_points": "[]",
            "difficulty": 2, "source": "", "estimated_time": 3,
        })
        q = importer._build_question_data(row)
        assert q.options == []
        assert q.id == "Q002"

    def test_build_embedding_content(self):
        row = pd.Series({
            "content": "求导题", "category": "导数",
            "knowledge_points": '["链式法则"]', "analysis": "详细解析" * 50,
        })
        content = QuestionImporter._build_embedding_content(row)
        assert "题目: 求导题" in content
        assert "分类: 导数" in content
        assert "知识点:" in content
        assert "解析:" in content


class TestQuestionImporterFile:
    """文件导入测试"""

    def test_import_from_csv_nonexistent(self):
        importer = QuestionImporter()

        async def _test():
            result = await importer.import_from_csv("nonexistent.csv")
            assert "文件不存在" in result.errors[0]

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())

    def test_import_from_excel_nonexistent(self):
        importer = QuestionImporter()

        async def _test():
            result = await importer.import_from_excel("nonexistent.xlsx")
            assert "文件不存在" in result.errors[0]

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


class TestImportResult:
    """ImportResult 数据类测试"""

    def test_default_values(self):
        r = ImportResult()
        assert r.total == 0
        assert r.success == 0
        assert r.failed == 0
        assert r.errors == []
        assert r.imported_ids == []

    def test_custom_values(self):
        r = ImportResult(total=10, success=8, failed=2, errors=["err1"], imported_ids=["Q1"])
        assert r.total == 10
        assert r.success == 8
        assert r.failed == 2
        assert "err1" in r.errors


# ═══════════════════════════════════════════════════════════════
# RAGRecommender 测试
# ═══════════════════════════════════════════════════════════════

class TestRAGRecommenderCore:
    """RAG 推荐器核心功能测试"""

    def test_question_to_dict_empty(self):
        assert RAGRecommender._question_to_dict(None) == {}

    @pytest.mark.asyncio
    async def test_determine_target_with_category(self):
        rec = RAGRecommender()
        target, weak = await rec._determine_target("导数", {}, {})
        assert target == "导数"
        assert weak == []

    @pytest.mark.asyncio
    async def test_determine_target_with_weak_points(self):
        rec = RAGRecommender()
        profile = {"weak_points": [{"category": "极限"}, {"category": "积分"}]}
        target, weak = await rec._determine_target("", {}, profile)
        assert target == "极限"
        assert len(weak) == 2

    @pytest.mark.asyncio
    async def test_determine_target_default(self):
        rec = RAGRecommender()
        target, weak = await rec._determine_target("", {}, {})
        assert target == "导数"
        assert weak == []

    def test_default_analysis(self):
        rec = RAGRecommender()
        analysis = rec._default_analysis(0.75, "导数", 5, 3)
        assert "75%" in analysis["assessment"]
        assert "难度3/5" in analysis["recommendation_reason"]
        assert analysis["estimated_time_minutes"] == 15


class TestRAGRecommenderFallback:
    """降级策略测试"""

    @pytest.mark.asyncio
    async def test_fallback_recommendation(self):
        rec = RAGRecommender()
        result = await rec._get_fallback_recommendation(
            RecommendationRequest(user_id="test", target_category="导数", count=3)
        )
        assert isinstance(result, RecommendationResult)
        assert result.meta.get("retrieval_method") == "fallback"
        assert result.meta.get("recommended_difficulty") == 3

    @pytest.mark.asyncio
    async def test_fallback_with_exclude(self):
        rec = RAGRecommender()
        result = await rec._get_fallback_recommendation(
            RecommendationRequest(user_id="test", count=2, exclude_ids=["Q001"])
        )
        assert isinstance(result, RecommendationResult)


class TestRAGRecommenderVectorRetrieval:
    """向量检索测试"""

    @pytest.mark.asyncio
    async def test_vector_retrieval_success(self):
        mock_vs = MagicMock()
        mock_vs.hybrid_search = AsyncMock(return_value=[
            VectorSearchResult(id="V1", content="test", metadata={"category": "导数", "difficulty": 3}, score=0.9, distance=0.1),
        ])
        rec = RAGRecommender(vector_store=mock_vs)
        results = await rec._vector_retrieval("导数", 3, 5)
        assert len(results) == 1
        assert results[0]["id"] == "V1"
        assert results[0]["source"] == "vector"

    @pytest.mark.asyncio
    async def test_vector_retrieval_error(self):
        mock_vs = MagicMock()
        mock_vs.hybrid_search = AsyncMock(side_effect=Exception("vector error"))
        rec = RAGRecommender(vector_store=mock_vs)
        results = await rec._vector_retrieval("导数", 3, 5)
        assert results == []


class TestRAGRecommenderKG:
    """知识图谱分析测试"""

    @pytest.mark.asyncio
    async def test_kg_analysis_no_match(self):
        rec = RAGRecommender()
        suggestions = await rec._kg_analysis("nonexistent_category", {})
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_kg_analysis_error(self):
        rec = RAGRecommender()
        # Use a category that doesn't exist in DAG to test error handling
        suggestions = await rec._kg_analysis("导数", {})
        assert isinstance(suggestions, list)


class TestRAGRecommenderFuse:
    """结果融合测试"""

    @pytest.mark.asyncio
    async def test_fuse_sql_only(self):
        from app.data.models import Question
        q1 = Question(id="Q1", content="c1", category="导数", difficulty=3, usage_count=5)
        q2 = Question(id="Q2", content="c2", category="导数", difficulty=3, usage_count=3)
        rec = RAGRecommender()
        result = await rec._fuse_and_rank(
            sql_results=[q1, q2], vector_results=[], kg_suggestions=[],
            target_count=2, difficulty=3,
        )
        assert len(result) == 2
        # Lower usage_count should come first
        assert result[0].id == "Q2"

    @pytest.mark.asyncio
    async def test_fuse_deduplication(self):
        from app.data.models import Question
        q1 = Question(id="Q1", content="c1", category="导数", difficulty=3, usage_count=0)
        rec = RAGRecommender()
        result = await rec._fuse_and_rank(
            sql_results=[q1], vector_results=[{"id": "Q1", "content": "c1"}],
            kg_suggestions=[], target_count=2, difficulty=3,
        )
        assert len(result) == 1


class TestRAGRecommenderUserProfile:
    """用户画像获取测试"""

    @pytest.mark.asyncio
    async def test_get_user_profile_error(self):
        rec = RAGRecommender()
        profile = await rec._get_user_profile("nonexistent_user")
        # Should return a dict with fallback values
        assert isinstance(profile, dict)
        assert "correct_rate" in profile
        assert "total_questions" in profile

    @pytest.mark.asyncio
    async def test_get_user_skills_error(self):
        rec = RAGRecommender()
        skills = await rec._get_user_skills_dict("nonexistent_user")
        assert skills == {}

    @pytest.mark.asyncio
    async def test_get_recently_done_error(self):
        rec = RAGRecommender()
        ids = await rec._get_recently_done_ids("nonexistent_user")
        assert ids == []


class TestRAGRecommenderRecommend:
    """推荐主流程测试"""

    @pytest.mark.asyncio
    async def test_recommend_success(self):
        from app.data.models import Question
        q = Question(id="Q001", content="测试题", question_type="选择题",
                     options=[], answer="A", category="导数", difficulty=3, usage_count=0)

        mock_vs = MagicMock()
        mock_vs.hybrid_search = AsyncMock(return_value=[])

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=LLMResponse(
            content='{"assessment":"好","recommendation_reason":"合适","learning_advice":"多练","estimated_time_minutes":15}',
            model="qwen-max", provider="dashscope",
        ))

        with patch.object(RAGRecommender, '_get_user_profile', new_callable=AsyncMock) as mock_profile, \
             patch.object(RAGRecommender, '_get_user_skills_dict', new_callable=AsyncMock) as mock_skills, \
             patch.object(RAGRecommender, '_get_recently_done_ids', new_callable=AsyncMock) as mock_done, \
             patch.object(RAGRecommender, '_sql_retrieval', new_callable=AsyncMock) as mock_sql:

            mock_profile.return_value = {"correct_rate": 0.8, "total_questions": 50}
            mock_skills.return_value = {}
            mock_done.return_value = []
            mock_sql.return_value = [q]

            rec = RAGRecommender(vector_store=mock_vs, llm_service=mock_llm)
            rec.enable_rag = True
            rec.enable_vector_search = True
            rec.enable_ai_explanation = True

            result = await rec.recommend(RecommendationRequest(
                user_id="test", target_category="导数", count=3,
            ))

            assert isinstance(result, RecommendationResult)
            assert len(result.questions) > 0
            assert result.questions[0]["id"] == "Q001"
            assert result.meta["retrieval_method"] == "hybrid"
            assert "ai_analysis" in result.__dict__

    @pytest.mark.asyncio
    async def test_recommend_fallback_on_error(self):
        rec = RAGRecommender()
        rec.enable_rag = True
        rec.enable_ai_explanation = True

        with patch.object(RAGRecommender, '_get_user_profile', new_callable=AsyncMock, side_effect=Exception("db error")):
            result = await rec.recommend(RecommendationRequest(
                user_id="test", target_category="导数", count=3,
            ))
            assert isinstance(result, RecommendationResult)
            assert result.meta["retrieval_method"] == "fallback"
            assert "error" in result.meta


class TestRAGRecommenderSingleton:
    """RAG 推荐器单例测试"""

    @pytest.mark.asyncio
    async def test_get_rag_recommender(self):
        with patch('app.services.vector_store.get_vector_store', new_callable=AsyncMock) as mock_vs, \
             patch('app.services.rag_recommender.get_llm_service') as mock_llm:
            mock_vs.return_value = MagicMock()
            mock_llm.return_value = MagicMock()
            rec = await get_rag_recommender()
            assert isinstance(rec, RAGRecommender)


# ═══════════════════════════════════════════════════════════════
# Tool 层测试
# ═══════════════════════════════════════════════════════════════

class TestRecommendTool:
    """推荐工具测试"""

    def test_get_info(self):
        from tools.recommend_tool import RecommendTool
        tool = RecommendTool()
        info = tool.get_info()
        assert info["name"] == "recommend_questions"
        assert "capabilities" in info
        assert "input_schema" in info

    def test_execute(self):
        from tools.recommend_tool import RecommendTool
        tool = RecommendTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="导数",
                parameters={"category": "导数", "count": 3, "context": "practice"},
                context={"user_id": "test_user"},
            ))
            # May fail due to missing DB, but should not crash
            assert isinstance(result, ToolOutput)

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


class TestSkillProfileTool:
    """技能画像工具测试"""

    def test_get_info(self):
        from tools.skill_profile_tool import SkillProfileTool
        tool = SkillProfileTool()
        info = tool.get_info()
        assert info["name"] == "skill_profile"
        assert "required" in info["input_schema"]

    def test_execute(self):
        from tools.skill_profile_tool import SkillProfileTool
        tool = SkillProfileTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="我的技能",
                parameters={},
                context={"user_id": "test_user"},
            ))
            assert isinstance(result, ToolOutput)

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


class TestExplainTool:
    """讲解工具测试"""

    def test_get_info(self):
        from tools.explain_tool import ExplainTool
        tool = ExplainTool()
        info = tool.get_info()
        assert info["name"] == "explain_question"
        assert ToolCapability.VERIFICATION.value in info["capabilities"]

    def test_execute_no_id(self):
        from tools.explain_tool import ExplainTool
        tool = ExplainTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="求导题",
                parameters={"question_content": "求 f(x)=x² 的导数"},
                context={},
            ))
            assert isinstance(result, ToolOutput)

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())

    def test_execute_invalid_id(self):
        from tools.explain_tool import ExplainTool
        tool = ExplainTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="",
                parameters={"question_id": "nonexistent_id"},
                context={},
            ))
            assert isinstance(result, ToolOutput)
            # Should fail gracefully
            assert result.success is False

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


class TestSearchTool:
    """搜索工具测试"""

    def test_get_info(self):
        from tools.search_tool import SearchTool
        tool = SearchTool()
        info = tool.get_info()
        assert info["name"] == "search_questions"
        assert "query" in info["input_schema"]["required"]

    def test_execute(self):
        from tools.search_tool import SearchTool
        tool = SearchTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="导数",
                parameters={"query": "导数", "limit": 3},
                context={},
            ))
            assert isinstance(result, ToolOutput)

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


class TestErrorBookTool:
    """错题本工具测试"""

    def test_get_info(self):
        from tools.error_book_tool import ErrorBookTool
        tool = ErrorBookTool()
        info = tool.get_info()
        assert info["name"] == "error_book_analysis"
        assert ToolCapability.ERROR_BOOK_MANAGEMENT.value in info["capabilities"]

    def test_execute(self):
        from tools.error_book_tool import ErrorBookTool
        tool = ErrorBookTool()

        async def _test():
            result = await tool.execute(ToolInput(
                query="我的错题",
                parameters={},
                context={"user_id": "test_user"},
            ))
            assert isinstance(result, ToolOutput)

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())


# ═══════════════════════════════════════════════════════════════
# BaseTool 测试
# ═══════════════════════════════════════════════════════════════

class TestBaseToolFields:
    """BaseTool 字段测试"""

    def test_tool_capability_values(self):
        assert ToolCapability.PRACTICE_GENERATION.value == "practice_generation"
        assert ToolCapability.KNOWLEDGE_RETRIEVAL.value == "knowledge_retrieval"
        assert ToolCapability.ERROR_BOOK_MANAGEMENT.value == "error_book_management"

    def test_tool_input_defaults(self):
        ti = ToolInput(query="test")
        assert ti.parameters == {}
        assert ti.context == {}

    def test_tool_output_defaults(self):
        to = ToolOutput(success=True)
        assert to.data == {}
        assert to.metadata == {}
        assert to.tool_name == ""
        assert to.execution_time_ms == 0.0

    def test_tool_output_with_data(self):
        to = ToolOutput(success=True, result="ok", data={"key": "val"}, tool_name="test_tool")
        assert to.data["key"] == "val"
        assert to.tool_name == "test_tool"


class TestConcreteTool:
    """具体工具实现测试"""

    def test_concrete_tool_execute(self):
        class MockTool(BaseTool):
            name = "mock_tool"
            description = "A mock tool"
            capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

            async def execute(self, input_data: ToolInput) -> ToolOutput:
                return ToolOutput(success=True, result="mock result", tool_name=self.name)

        async def _test():
            tool = MockTool()
            result = await tool.execute(ToolInput(query="test"))
            assert result.success is True
            assert result.result == "mock result"

        import asyncio
        asyncio.get_event_loop().run_until_complete(_test())

    def test_get_description_for_llm(self):
        class MockTool(BaseTool):
            name = "mock_tool"
            description = "A mock tool"
            capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

            async def execute(self, input_data: ToolInput) -> ToolOutput:
                return ToolOutput(success=True)

        tool = MockTool()
        desc = tool.get_description_for_llm()
        assert "mock_tool" in desc
        assert "A mock tool" in desc
        assert "knowledge_retrieval" in desc

    def test_validate_input_empty(self):
        class MockTool(BaseTool):
            name = "mock_tool"
            description = "A mock tool"
            capabilities = []

            async def execute(self, input_data: ToolInput) -> ToolOutput:
                return ToolOutput(success=True)

        tool = MockTool()
        error = tool.validate_input(ToolInput(query=""))
        assert error is not None
        assert "不能为空" in error

        error2 = tool.validate_input(ToolInput(query="valid"))
        assert error2 is None