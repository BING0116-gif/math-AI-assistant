"""
VectorStoreManager 单元测试。

覆盖：
- 元数据清理
- 搜索结果格式化
- 关键词评分
- 混合搜索
- 单例和工厂函数
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.vector_store import (
    VectorStoreManager,
    VectorSearchResult,
    get_vector_store,
)


class TestMetadataCleaning:
    """测试元数据清理"""

    def test_clean_simple_types(self):
        """保留 str/int/float/bool 类型"""
        metadata = {
            "category": "calculus",
            "difficulty": 3,
            "score": 0.95,
            "active": True,
        }
        cleaned = VectorStoreManager._clean_metadata(metadata)
        assert cleaned == metadata

    def test_clean_none_values_removed(self):
        """移除 None 值"""
        metadata = {"category": "calculus", "difficulty": None, "name": "test"}
        cleaned = VectorStoreManager._clean_metadata(metadata)
        assert "difficulty" not in cleaned
        assert "category" in cleaned
        assert cleaned["category"] == "calculus"

    def test_clean_list_to_json(self):
        """列表转为 JSON 字符串"""
        metadata = {"tags": ["math", "calculus"], "name": "test"}
        cleaned = VectorStoreManager._clean_metadata(metadata)
        assert isinstance(cleaned["tags"], str)
        assert "math" in cleaned["tags"]

    def test_clean_dict_to_json(self):
        """字典转为 JSON 字符串"""
        metadata = {"config": {"key": "value"}, "name": "test"}
        cleaned = VectorStoreManager._clean_metadata(metadata)
        assert isinstance(cleaned["config"], str)

    def test_clean_other_types_to_string(self):
        """其他类型转为字符串"""
        metadata = {"name": "test", "obj": object()}
        cleaned = VectorStoreManager._clean_metadata(metadata)
        assert isinstance(cleaned["obj"], str)


class TestVectorSearchResult:
    """测试 VectorSearchResult 数据类"""

    def test_creation(self):
        result = VectorSearchResult(
            id="q1",
            content="test content",
            metadata={"category": "math"},
            score=0.85,
            distance=0.15,
        )
        assert result.id == "q1"
        assert result.content == "test content"
        assert result.score == 0.85
        assert result.distance == 0.15


class TestFormatResults:
    """测试搜索结果格式化"""

    @pytest.fixture
    def manager(self):
        mgr = VectorStoreManager.__new__(VectorStoreManager)
        return mgr

    def test_empty_results(self, manager):
        results = manager._format_results({"ids": [], "documents": [], "metadatas": [], "distances": []})
        assert results == []

    def test_none_results(self, manager):
        results = manager._format_results(None)
        assert results == []

    def test_valid_results(self, manager):
        raw = {
            "ids": [["q1", "q2"]],
            "documents": [["content 1", "content 2"]],
            "metadatas": [[{"cat": "math"}, {"cat": "physics"}]],
            "distances": [[0.1, 0.3]],
        }
        results = manager._format_results(raw)
        assert len(results) == 2
        assert results[0].id == "q1"
        assert results[0].score == 0.9  # 1.0 - 0.1
        assert results[1].id == "q2"
        assert results[1].score == 0.7  # 1.0 - 0.3


class TestKeywordScores:
    """测试关键词评分"""

    @pytest.fixture
    def manager(self):
        mgr = VectorStoreManager.__new__(VectorStoreManager)
        return mgr

    def test_chinese_keywords(self, manager):
        results = [
            VectorSearchResult(id="q1", content="计算极限题目", metadata={}, score=0.8, distance=0.2),
            VectorSearchResult(id="q2", content="微分方程求解", metadata={}, score=0.6, distance=0.4),
        ]
        scores = manager._calculate_keyword_scores("极限", results)
        assert scores["q1"] > scores["q2"]

    def test_english_keywords(self, manager):
        results = [
            VectorSearchResult(id="q1", content="calculate integral", metadata={}, score=0.8, distance=0.2),
            VectorSearchResult(id="q2", content="solve derivative", metadata={}, score=0.6, distance=0.4),
        ]
        scores = manager._calculate_keyword_scores("integral", results)
        assert scores["q1"] > scores["q2"]

    def test_metadata_keywords(self, manager):
        results = [
            VectorSearchResult(id="q1", content="test", metadata={"category": "calculus"}, score=0.8, distance=0.2),
            VectorSearchResult(id="q2", content="test", metadata={"category": "algebra"}, score=0.6, distance=0.4),
        ]
        scores = manager._calculate_keyword_scores("calculus", results)
        assert scores["q1"] > scores["q2"]

    def test_no_keywords(self, manager):
        results = [
            VectorSearchResult(id="q1", content="test", metadata={}, score=0.8, distance=0.2),
        ]
        scores = manager._calculate_keyword_scores("123", results)
        assert scores == {}


class TestVectorStoreManager:
    """测试 VectorStoreManager 实例"""

    @pytest.fixture
    def manager(self):
        mgr = VectorStoreManager.__new__(VectorStoreManager)
        mgr.persist_directory = "/tmp/test_chroma"
        mgr.collection_name = "test_collection"
        mgr._client = None
        mgr._collection = None
        mgr._initialized = False
        return mgr

    @pytest.mark.asyncio
    async def test_initialize(self, manager):
        """测试初始化"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("chromadb.PersistentClient", return_value=mock_client):
            with patch("os.makedirs"):
                await manager.initialize()
                assert manager._initialized is True
                assert manager._client is not None

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, manager):
        """初始化是幂等的"""
        manager._initialized = True
        await manager.initialize()
        # 不应报错

    @pytest.mark.asyncio
    async def test_add_question(self, manager):
        """测试添加题目"""
        mock_collection = MagicMock()
        manager._collection = mock_collection
        manager._initialized = True

        result = await manager.add_question(
            "q1", "test content", {"category": "math"}
        )
        assert result is True
        mock_collection.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_question_failure(self, manager):
        """测试添加失败"""
        mock_collection = MagicMock()
        mock_collection.add.side_effect = Exception("DB error")
        manager._collection = mock_collection
        manager._initialized = True

        result = await manager.add_question("q1", "test", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_question(self, manager):
        """测试移除题目"""
        mock_collection = MagicMock()
        manager._collection = mock_collection
        manager._initialized = True

        result = await manager.remove_question("q1")
        assert result is True
        mock_collection.delete.assert_called_once_with(ids=["q1"])

    @pytest.mark.asyncio
    async def test_semantic_search(self, manager):
        """测试语义搜索"""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["q1"]],
            "documents": [["test content"]],
            "metadatas": [[{"category": "math"}]],
            "distances": [[0.2]],
        }
        manager._collection = mock_collection
        manager._initialized = True

        results = await manager.semantic_search("test query", n_results=5)
        assert len(results) == 1
        assert results[0].id == "q1"
        mock_collection.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_search_error(self, manager):
        """测试搜索错误"""
        mock_collection = MagicMock()
        mock_collection.query.side_effect = Exception("search error")
        manager._collection = mock_collection
        manager._initialized = True

        results = await manager.semantic_search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_all_ids_empty(self, manager):
        """测试空集合获取 ID"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        manager._collection = mock_collection
        manager._initialized = True

        ids = await manager.get_all_ids()
        assert ids == []

    @pytest.mark.asyncio
    async def test_get_collection_stats(self, manager):
        """测试获取集合统计"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 2
        mock_collection.get.return_value = {
            "metadatas": [
                {"category": "math", "difficulty": 3},
                {"category": "physics", "difficulty": 5},
            ]
        }
        manager._collection = mock_collection
        manager._initialized = True

        stats = await manager.get_collection_stats()
        assert stats["total_documents"] == 2
        assert "math" in stats["categories"]
        assert "physics" in stats["categories"]

    @pytest.mark.asyncio
    async def test_update_question_not_found(self, manager):
        """测试更新不存在的题目"""
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": []}
        manager._collection = mock_collection
        manager._initialized = True

        result = await manager.update_question("q1", content="new content")
        assert result is False