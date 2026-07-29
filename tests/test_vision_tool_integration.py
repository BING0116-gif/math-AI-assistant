"""
Vision Tool Integration Test

Test the actual API call functionality using pytest-asyncio.
"""

import sys
import os
import pytest

# Add project root to Python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="需要 DASHSCOPE_API_KEY 环境变量"
)
@pytest.mark.asyncio
async def test_vision_tool_api():
    """Test VisionTool API call."""
    from tools.vision_tool import VisionTool
    from app.config.settings import settings

    api_key = settings.DASHSCOPE_API_KEY
    assert api_key, "DASHSCOPE_API_KEY not configured"

    # Create VisionTool instance
    vision = VisionTool(api_key=api_key)
    assert vision._model == "qwen-vl-plus"

    # Create a simple test image
    import tempfile
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new('RGB', (100, 100), color='red')
        img.save(f, 'PNG')
        test_image_path = f.name

    try:
        # Call recognize
        result = vision.recognize(test_image_path)

        assert result["success"], f"API call failed: {result.get('error')}"
        assert result["model_used"] == "qwen-vl-plus"
        assert len(result.get("raw_response", "")) > 0

    finally:
        if os.path.exists(test_image_path):
            os.unlink(test_image_path)


@pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="需要 DASHSCOPE_API_KEY 环境变量"
)
@pytest.mark.asyncio
async def test_vision_tool_adapter():
    """Test VisionToolAdapter with BaseTool interface."""
    from tools.vision_tool import VisionTool, VisionToolAdapter
    from tools.base_tool import ToolInput
    from app.config.settings import settings

    api_key = settings.DASHSCOPE_API_KEY
    assert api_key, "DASHSCOPE_API_KEY not configured"

    # Create adapter
    vision = VisionTool(api_key=api_key)
    adapter = VisionToolAdapter(vision)

    assert adapter.name == "vision_tool"
    assert adapter.version == "2.0.0"

    # Create test image
    import tempfile
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(f, 'PNG')
        test_image_path = f.name

    try:
        tool_input = ToolInput(
            query=test_image_path,
            parameters={"image_source": test_image_path}
        )

        result = await adapter.execute(tool_input)

        assert result.success, f"Adapter failed: {result.error}"
        assert result.tool_name == "vision_tool"
        assert result.result is not None

    finally:
        if os.path.exists(test_image_path):
            os.unlink(test_image_path)


@pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="需要 DASHSCOPE_API_KEY 环境变量"
)
@pytest.mark.asyncio
async def test_registry_execution():
    """Test tool execution through registry."""
    from tools import get_registry, _register_builtin_tools
    from tools.base_tool import ToolInput
    from PIL import Image
    import tempfile

    registry = get_registry()
    # 如果注册表为空，重新注册工具
    if registry.tool_count == 0:
        _register_builtin_tools(registry)
    from app.config.settings import settings
    if settings.DASHSCOPE_API_KEY:
        assert registry.has_tool("vision_tool"), "vision_tool not registered"

    # Create test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new('RGB', (100, 100), color='green')
        img.save(f, 'PNG')
        test_image_path = f.name

    try:
        tool_input = ToolInput(
            query=test_image_path,
            parameters={"image_source": test_image_path}
        )

        result = await registry.execute_safe("vision_tool", tool_input)

        assert result.success, f"Registry execution failed: {result.error}"
        assert result.tool_name == "vision_tool"
        assert result.result is not None

    finally:
        if os.path.exists(test_image_path):
            os.unlink(test_image_path)


if __name__ == "__main__":
    # Allow running directly with asyncio
    import asyncio
    asyncio.run(test_vision_tool_api())
    asyncio.run(test_vision_tool_adapter())
    asyncio.run(test_registry_execution())
