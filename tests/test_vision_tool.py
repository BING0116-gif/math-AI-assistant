"""
VisionTool 单元测试

测试 VisionTool 和 VisionToolAdapter 的各项功能。
"""

import pytest
import asyncio
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ── 测试夹具（Fixtures）────────────────────────────────────────────────────

@pytest.fixture
def mock_api_key():
    """模拟 API Key。"""
    return "test-api-key-12345"


@pytest.fixture
def mock_response():
    """模拟 VL API 响应。"""
    return {
        "choices": [{
            "message": {
                "content": "【题目】\n求极限\n\n【公式】\n$$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$$\n\n【选项】\nA. 0\nB. 1\nC. 2\nD. 不存在"
            }
        }]
    }


@pytest.fixture
def temp_image():
    """创建临时测试图片。"""
    from PIL import Image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new('RGB', (100, 100), color='red')
        img.save(f, 'PNG')
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


# ── VisionTool 单元测试 ──────────────────────────────────────────────────

class TestVisionToolBasics:
    """VisionTool 基础功能测试。"""

    def test_init_with_api_key(self, mock_api_key):
        """测试使用 API Key 初始化。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)

        assert tool._api_key == mock_api_key
        assert tool._model == "qwen-vl-plus"
        assert tool.name == "vision_tool"
        assert "qwen-vl" in tool.description.lower()

    def test_init_with_custom_model(self, mock_api_key):
        """测试使用自定义模型初始化。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(model="qwen-vl-max", api_key=mock_api_key)

        assert tool._model == "qwen-vl-max"

    def test_init_without_api_key(self, monkeypatch):
        """测试未提供 API Key 时的行为。"""
        from tools.vision_tool import VisionTool

        # Mock the _load_api_key function to return None
        with patch('tools.vision_tool._load_api_key', return_value=None):
            tool = VisionTool(api_key=None)

            assert tool._api_key is None
            assert tool.api_key_configured is False

    def test_build_headers(self, mock_api_key):
        """测试请求头构建。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        headers = tool._build_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == f"Bearer {mock_api_key}"
        assert headers["Content-Type"] == "application/json"

    def test_build_image_url_from_file(self, temp_image, mock_api_key):
        """测试从文件构建图片 URL。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        image_url = tool._build_image_url(temp_image)

        assert image_url.startswith("data:image/png;base64,")

    def test_build_image_url_from_tuple(self, mock_api_key):
        """测试从元组构建图片 URL。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        image_url = tool._build_image_url(("image/png", "test-base64-data"))

        assert image_url == "data:image/png;base64,test-base64-data"

    def test_build_image_url_file_not_found(self, mock_api_key):
        """测试文件不存在时的错误处理。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)

        with pytest.raises(FileNotFoundError):
            tool._build_image_url("/nonexistent/image.png")

    def test_build_messages(self, mock_api_key):
        """测试消息构建。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        messages = tool._build_messages(
            image_url="data:image/png;base64,test",
            user_prompt="识别这张图片"
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert len(messages[1]["content"]) == 2  # text + image

    def test_get_models_to_try(self, mock_api_key):
        """测试模型列表构建。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)

        # 指定模型
        models = tool._get_models_to_try("qwen-vl-max")
        assert models[0] == "qwen-vl-max"
        assert "qwen-vl-plus" in models

        # 默认模型
        models = tool._get_models_to_try(None)
        assert models[0] == "qwen-vl-plus"


class TestVisionToolRecognize:
    """VisionTool.recognize() 方法测试。"""

    @patch('httpx.Client')
    def test_recognize_success(self, mock_client_class, temp_image, mock_api_key, mock_response):
        """测试识别成功场景。"""
        from tools.vision_tool import VisionTool

        # Mock httpx response
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response_obj
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client

        tool = VisionTool(api_key=mock_api_key)
        result = tool.recognize(temp_image)

        assert result["success"] is True
        assert result["model_used"] == "qwen-vl-plus"
        assert "【题目】" in result["raw_response"]
        assert "llm_description" in result

    def test_recognize_no_api_key(self, monkeypatch):
        """测试未配置 API Key 的错误处理。"""
        from tools.vision_tool import VisionTool

        # Mock the _load_api_key function to return None
        with patch('tools.vision_tool._load_api_key', return_value=None):
            tool = VisionTool(api_key=None)
            result = tool.recognize("test.png")

            assert result["success"] is False
            assert "API_KEY" in result["error"]

    def test_recognize_file_not_found(self, mock_api_key):
        """测试文件不存在的错误处理。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        result = tool.recognize("/nonexistent/image.png")

        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_recognize_from_base64(self, mock_api_key, mock_response):
        """测试从 base64 识别。"""
        from tools.vision_tool import VisionTool

        with patch('httpx.Client') as mock_client_class:
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response_obj
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            tool = VisionTool(api_key=mock_api_key)
            result = tool.recognize_from_base64(
                mime="image/png",
                b64_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )

            assert result["success"] is True


class TestVisionToolParseResponse:
    """响应解析测试。"""

    def test_parse_response_success(self, mock_api_key, mock_response):
        """测试成功响应解析。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        result = tool._parse_response(mock_response, "qwen-vl-plus")

        assert result["success"] is True
        assert result["model_used"] == "qwen-vl-plus"
        assert "【题目】" in result["raw_response"]
        assert "llm_description" in result
        assert "请解答以下" in result["llm_description"]

    def test_parse_response_no_choices(self, mock_api_key):
        """测试无 choices 响应。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        result = tool._parse_response({"error": "rate limit"}, "qwen-vl-plus")

        assert result["success"] is False
        assert "choices" in result["error"]

    def test_error_result(self, mock_api_key):
        """测试错误结果构建。"""
        from tools.vision_tool import VisionTool

        tool = VisionTool(api_key=mock_api_key)
        result = tool._error_result("Test error message")

        assert result["success"] is False
        assert result["error"] == "Test error message"
        assert result["llm_description"] == ""
        assert result["model_used"] == ""


# ── VisionToolAdapter 单元测试 ────────────────────────────────────────────

class TestVisionToolAdapter:
    """VisionToolAdapter 测试。"""

    @pytest.fixture
    def mock_vision_tool(self, mock_api_key):
        """创建模拟 VisionTool。"""
        from tools.vision_tool import VisionTool
        return VisionTool(api_key=mock_api_key)

    def test_adapter_init(self, mock_vision_tool):
        """测试适配器初始化。"""
        from tools.vision_tool import VisionToolAdapter

        adapter = VisionToolAdapter(mock_vision_tool)

        assert adapter.name == "vision_tool"
        assert adapter.version == "2.0.0"
        assert "image_recognition" in [c.value for c in adapter.capabilities]
        assert "formula_recognition" in [c.value for c in adapter.capabilities]

    def test_get_info(self, mock_vision_tool):
        """测试获取工具信息。"""
        from tools.vision_tool import VisionToolAdapter

        adapter = VisionToolAdapter(mock_vision_tool)
        info = adapter.get_info()

        assert info["name"] == "vision_tool"
        assert info["version"] == "2.0.0"
        assert "capabilities" in info
        assert "api_configured" in info
        assert info["api_configured"] is True

    def test_validate_input_valid(self, mock_vision_tool):
        """测试有效输入验证。"""
        from tools.vision_tool import VisionToolAdapter
        from tools.base_tool import ToolInput

        adapter = VisionToolAdapter(mock_vision_tool)
        input_data = ToolInput(query="test.png", parameters={"image_source": "test.png"})

        assert adapter.validate_input(input_data) is None

    def test_validate_input_empty(self, mock_vision_tool):
        """测试空输入验证。"""
        from tools.vision_tool import VisionToolAdapter
        from tools.base_tool import ToolInput

        adapter = VisionToolAdapter(mock_vision_tool)
        input_data = ToolInput(query="", parameters={})

        error = adapter.validate_input(input_data)
        assert error is not None
        assert "不能为空" in error

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.environ.get("DASHSCOPE_API_KEY"),
        reason="需要 DASHSCOPE_API_KEY 环境变量"
    )
    async def test_execute_success(self, mock_vision_tool, temp_image, mock_response):
        """测试异步执行成功。"""
        from tools.vision_tool import VisionToolAdapter
        from tools.base_tool import ToolInput

        # Mock recognize_stream to avoid actual API calls
        async def _mock_stream(*args, **kwargs):
            yield {"type": "complete", "success": True, "model_used": "qwen-vl-plus", "content": "test", "llm_description": "test result", "raw_response": "test"}
        mock_vision_tool.recognize_stream = _mock_stream

        adapter = VisionToolAdapter(mock_vision_tool)
        input_data = ToolInput(
            query=temp_image,
            parameters={"image_source": temp_image}
        )

        result = await adapter.execute(input_data)

        assert result.success is True
        assert result.tool_name == "vision_tool"
        assert result.result is not None
        assert "metadata" in result.model_dump()

    @pytest.mark.asyncio
    async def test_execute_no_api_key(self, monkeypatch):
        """测试未配置 API Key 的错误处理。"""
        from tools.vision_tool import VisionTool, VisionToolAdapter
        from tools.base_tool import ToolInput

        # Mock to return None API key
        with patch('tools.vision_tool._load_api_key', return_value=None):
            tool = VisionTool(api_key=None)
            adapter = VisionToolAdapter(tool)

            input_data = ToolInput(query="test.png")
            result = await adapter.execute(input_data)

            assert result.success is False
            assert "API_KEY" in result.error


# ── 辅助函数测试 ──────────────────────────────────────────────────────────

class TestHelperFunctions:
    """辅助函数测试。"""

    def test_load_api_key_from_env(self):
        """测试从环境变量加载 API Key。"""
        import os
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            pytest.skip("DASHSCOPE_API_KEY 未设置，跳过测试")

        from tools.vision_tool import _load_api_key

        key = _load_api_key()
        assert key == api_key

    def test_guess_mime(self):
        """测试 MIME 类型推断。"""
        from tools.vision_tool import _guess_mime

        assert _guess_mime("test.jpg") == "image/jpeg"
        assert _guess_mime("test.png") == "image/png"
        assert _guess_mime("test.webp") == "image/webp"
        assert _guess_mime("test.unknown") == "image/png"  # 默认值

    def test_build_llm_input(self):
        """测试 LLM 输入构建。"""
        from tools.vision_tool import _build_llm_input

        vl_output = "【题目】\n求极限\n\n【公式】\n$$\\lim_{x \\to 0}$$"

        result = _build_llm_input(vl_output)

        assert "请解答以下" in result
        assert "【题目】" in result
        assert "高等数学" in result


# ── 运行入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
