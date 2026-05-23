"""
ToolRegistry 单元测试。

覆盖 BaseTool、ToolRegistry、VisionToolAdapter 的所有核心功能。
"""

import pytest
import asyncio
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.hybrid_registry import (
    HybridToolRegistry as ToolRegistry,
    ToolNotFoundError,
    ToolExecutionError,
)
from tools.vision_tool import VisionTool, VisionToolAdapter


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class DummyTool(BaseTool):
    """测试用工具实现。"""

    description = "用于测试的虚拟工具"
    version = "1.0.0"
    capabilities = [
        ToolCapability.SYMBOLIC_COMPUTATION,
        ToolCapability.VERIFICATION,
    ]

    def __init__(
        self,
        fail_on_execute: bool = False,
        tool_name: str = "dummy_tool",
    ):
        self._fail_on_execute = fail_on_execute
        self._tool_name = tool_name

    @property
    def name(self) -> str:
        return self._tool_name

    @name.setter
    def name(self, value: str) -> None:
        self._tool_name = value

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        if self._fail_on_execute:
            raise RuntimeError("Intentional test failure")
        return ToolOutput(
            success=True,
            result=f"processed: {input_data.query}",
            tool_name=self._tool_name,
        )


class FailingTool(BaseTool):
    """始终在 validate_input 中失败的测试工具。"""

    name = "failing_tool"
    description = "校验失败的测试工具"
    version = "1.0.0"
    capabilities = [ToolCapability.NUMERICAL_COMPUTATION]

    def validate_input(self, input_data: ToolInput) -> Optional[str]:
        return "This tool always fails validation"

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        return ToolOutput(success=True, result="x", tool_name=self.name)


class ExceptionTool(BaseTool):
    """始终在 execute 中抛出异常的测试工具。"""

    name = "exception_tool"
    description = "执行时抛异常的测试工具"
    version = "1.0.0"
    capabilities = [ToolCapability.PLOTTING]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        raise RuntimeError("Test exception")


class MockVisionTool:
    def __init__(self, should_fail: bool = False):
        self._should_fail = should_fail

    async def recognize_stream(self, image_source, user_prompt=None):
        if self._should_fail:
            yield {"type": "complete", "content": "Mock recognition error", "success": False,
                   "llm_description": "", "raw_response": "", "model_used": ""}
        else:
            yield {"type": "complete", "content": "识别完成", "success": True,
                   "llm_description": "Mock image description",
                   "raw_response": "Mock raw response", "model_used": "mock-vl"}


# ---------------------------------------------------------------------------
# BaseTool tests
# ---------------------------------------------------------------------------

class TestBaseToolGetInfo:
    def test_returns_all_fields(self):
        tool = DummyTool()
        info = tool.get_info()
        assert info["name"] == "dummy_tool"
        assert info["description"] == "用于测试的虚拟工具"
        assert info["version"] == "1.0.0"
        assert info["capabilities"] == [
            "symbolic_computation",
            "verification",
        ]
        assert "input_schema" in info

    def test_capabilities_serialized_as_strings(self):
        tool = DummyTool()
        info = tool.get_info()
        assert all(isinstance(c, str) for c in info["capabilities"])


class TestBaseToolGetDescriptionForLLM:
    def test_format_includes_all_fields(self):
        tool = DummyTool()
        desc = tool.get_description_for_llm()
        assert "工具名: dummy_tool" in desc
        assert "用于测试的虚拟工具" in desc
        assert "symbolic_computation" in desc
        assert "verification" in desc
        assert "1.0.0" in desc


class TestBaseToolValidateInput:
    def test_empty_query_returns_error(self):
        tool = DummyTool()
        result = tool.validate_input(ToolInput(query="   "))
        assert result is not None

    def test_valid_query_returns_none(self):
        tool = DummyTool()
        result = tool.validate_input(ToolInput(query="求积分 x^2"))
        assert result is None

    def test_empty_string_returns_error(self):
        tool = DummyTool()
        result = tool.validate_input(ToolInput(query=""))
        assert result is not None


class TestBaseToolCannotInstantiate:
    def test_abstract_class_raises_error(self):
        with pytest.raises(TypeError):
            BaseTool()


# ---------------------------------------------------------------------------
# ToolRegistry registration tests
# ---------------------------------------------------------------------------

class TestRegistryRegister:
    def test_register_increases_count(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        assert registry.tool_count == 1

    def test_register_multiple_tools(self):
        registry = ToolRegistry()
        registry.register(DummyTool(tool_name="tool_a"))
        registry.register(DummyTool(tool_name="tool_b"))
        assert registry.tool_count == 2

    def test_empty_name_raises(self):
        registry = ToolRegistry()
        tool = DummyTool()
        tool.name = ""
        with pytest.raises(ValueError, match="name 属性不能为空"):
            registry.register(tool)

    def test_duplicate_overwrites_with_warning(self, caplog):
        registry = ToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool()
        t2.version = "2.0.0"
        registry.register(t1)
        with caplog.at_level("WARNING"):
            registry.register(t2)
        assert "将被覆盖为 v2.0.0" in caplog.text
        assert registry.tool_count == 1
        assert registry.get_tool("dummy_tool").version == "2.0.0"


class TestRegistryUnregister:
    def test_unregister_existing(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        assert registry.unregister("dummy_tool") is True
        assert registry.tool_count == 0

    def test_unregister_nonexistent(self):
        registry = ToolRegistry()
        assert registry.unregister("nonexistent") is False

    def test_unregister_decreases_count(self):
        registry = ToolRegistry()
        registry.register(DummyTool(tool_name="tool_a"))
        registry.register(DummyTool(tool_name="tool_b"))
        assert registry.tool_count == 2
        registry.unregister("tool_a")
        assert registry.tool_count == 1


# ---------------------------------------------------------------------------
# ToolRegistry query tests
# ---------------------------------------------------------------------------

class TestRegistryGetTool:
    def test_get_existing_tool(self):
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        assert registry.get_tool("dummy_tool") is tool

    def test_get_nonexistent_raises(self):
        registry = ToolRegistry()
        with pytest.raises(ToolNotFoundError, match="工具未注册"):
            registry.get_tool("nonexistent")


class TestRegistryHasTool:
    def test_has_registered_tool(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        assert registry.has_tool("dummy_tool") is True

    def test_does_not_have_unregistered_tool(self):
        registry = ToolRegistry()
        assert registry.has_tool("dummy_tool") is False


class TestRegistrySearchTools:
    def test_search_by_matching_capability(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("symbolic_computation")
        assert "dummy_tool" in result

    def test_search_by_nonmatching_capability(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("plotting")
        assert "dummy_tool" not in result

    def test_search_empty_registry(self):
        registry = ToolRegistry()
        assert registry.search_tools("symbolic_computation") == []

    def test_search_case_sensitive(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("SYMBOLIC_COMPUTATION")
        assert "dummy_tool" not in result


class TestRegistryListTools:
    def test_list_returns_all_tools(self):
        registry = ToolRegistry()
        registry.register(DummyTool(tool_name="tool_x"))
        registry.register(DummyTool(tool_name="tool_y"))
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_list_empty_registry(self):
        registry = ToolRegistry()
        assert registry.list_tools() == []


class TestRegistryGetAllDescriptions:
    def test_returns_formatted_descriptions(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        desc = registry.get_all_descriptions()
        assert "当前可用工具列表" in desc
        assert "dummy_tool" in desc

    def test_empty_registry_returns_message(self):
        registry = ToolRegistry()
        assert registry.get_all_descriptions() == "当前无可用工具。"

    def test_multiple_tools_all_included(self):
        registry = ToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool(tool_name="another_tool")
        registry.register(t1)
        registry.register(t2)
        desc = registry.get_all_descriptions()
        assert "dummy_tool" in desc
        assert "another_tool" in desc


class TestRegistryGetToolsByNames:
    def test_returns_only_existing_tools(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        tools = registry.get_tools_by_names(["dummy_tool", "nonexistent"])
        assert len(tools) == 1
        assert tools[0].name == "dummy_tool"

    def test_empty_list_returns_empty(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        tools = registry.get_tools_by_names([])
        assert tools == []

    def test_skips_nonexistent_with_warning(self, caplog):
        registry = ToolRegistry()
        registry.register(DummyTool())
        with caplog.at_level("WARNING"):
            registry.get_tools_by_names(["nonexistent"])
        assert "已跳过" in caplog.text


class TestRegistryToolNames:
    def test_returns_all_registered_names(self):
        registry = ToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool(tool_name="tool_b")
        registry.register(t1)
        registry.register(t2)
        names = registry.tool_names
        assert "dummy_tool" in names
        assert "tool_b" in names

    def test_empty_registry_returns_empty_list(self):
        registry = ToolRegistry()
        assert registry.tool_names == []


# ---------------------------------------------------------------------------
# ToolRegistry execute tests
# ---------------------------------------------------------------------------

class TestRegistryExecuteSafe:
    def test_execute_success(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test query"))
        )
        assert result.success is True
        assert "processed: test query" in result.result

    def test_execute_tool_not_found(self):
        registry = ToolRegistry()
        result = asyncio.run(
            registry.execute_safe("nonexistent", ToolInput(query="test"))
        )
        assert result.success is False
        assert "工具未注册" in result.error

    def test_execute_validation_fails(self):
        registry = ToolRegistry()
        registry.register(FailingTool())
        result = asyncio.run(
            registry.execute_safe("failing_tool", ToolInput(query="anything"))
        )
        assert result.success is False
        assert "输入校验失败" in result.error

    def test_execute_exception_returns_tool_output(self):
        registry = ToolRegistry()
        registry.register(DummyTool(fail_on_execute=True))
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test"))
        )
        assert result.success is False
        assert "RuntimeError" in result.error

    def test_execution_time_recorded(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test"))
        )
        assert result.execution_time_ms >= 0
        assert result.tool_name == "dummy_tool"

    def test_multiple_calls_update_stats(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2
        assert stats["success_count"] == 2


# ---------------------------------------------------------------------------
# ToolRegistry execution history and stats tests
# ---------------------------------------------------------------------------

class TestRegistryExecutionStats:
    def test_empty_registry_stats(self):
        registry = ToolRegistry()
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 0.0

    def test_stats_after_successful_calls(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 1.0

    def test_stats_mixed_success_failure(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        registry.register(ExceptionTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="ok")))
        asyncio.run(registry.execute_safe("exception_tool", ToolInput(query="fail")))
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == 0.5

    def test_tool_specific_stats(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert "dummy_tool" in stats["tool_stats"]
        assert stats["tool_stats"]["dummy_tool"]["calls"] == 2
        assert stats["tool_stats"]["dummy_tool"]["successes"] == 2

    def test_history_max_size_enforced(self):
        registry = ToolRegistry()
        registry._max_history = 5
        registry.register(DummyTool())
        for i in range(10):
            asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query=f"q{i}")))
        assert len(registry._execution_history) == 5


# ---------------------------------------------------------------------------
# VisionToolAdapter tests
# ---------------------------------------------------------------------------

class TestVisionToolAdapterInheritance:
    def test_isinstance_of_basetool(self):
        mock_vt = MockVisionTool()
        adapter = VisionToolAdapter(mock_vt)
        assert isinstance(adapter, BaseTool)

    def test_adapter_has_correct_capabilities(self):
        mock_vt = MockVisionTool()
        adapter = VisionToolAdapter(mock_vt)
        assert ToolCapability.IMAGE_RECOGNITION in adapter.capabilities
        assert ToolCapability.FORMULA_RECOGNITION in adapter.capabilities

    def test_adapter_name(self):
        mock_vt = MockVisionTool()
        adapter = VisionToolAdapter(mock_vt)
        assert adapter.name == "vision_tool"

    def test_adapter_description(self):
        mock_vt = MockVisionTool()
        adapter = VisionToolAdapter(mock_vt)
        assert "Qwen-VL" in adapter.description


class TestVisionToolAdapterExecute:
    def test_execute_success(self):
        mock_vt = MockVisionTool(should_fail=False)
        adapter = VisionToolAdapter(mock_vt)
        result = asyncio.run(
            adapter.execute(
                ToolInput(query="test.jpg", parameters={"image_source": "test.jpg"})
            )
        )
        assert result.success is True
        assert "Mock image description" in result.result
        assert result.tool_name == "vision_tool"
        assert result.metadata["model_used"] == "mock-vl"

    def test_execute_failure(self):
        mock_vt = MockVisionTool(should_fail=True)
        adapter = VisionToolAdapter(mock_vt)
        result = asyncio.run(
            adapter.execute(
                ToolInput(query="test.jpg", parameters={"image_source": "test.jpg"})
            )
        )
        assert result.success is False
        assert "Mock recognition error" in result.error
        assert result.tool_name == "vision_tool"

    def test_execute_with_user_prompt(self):
        mock_vt = MockVisionTool(should_fail=False)
        adapter = VisionToolAdapter(mock_vt)
        result = asyncio.run(
            adapter.execute(
                ToolInput(
                    query="test.jpg",
                    parameters={"image_source": "test.jpg", "user_prompt": "describe"},
                )
            )
        )
        assert result.success is True

    def test_execute_with_query_as_image_source(self):
        mock_vt = MockVisionTool(should_fail=False)
        adapter = VisionToolAdapter(mock_vt)
        result = asyncio.run(
            adapter.execute(
                ToolInput(query="/path/to/image.png")
            )
        )
        assert result.success is True
        assert "Mock image description" in result.result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_full_tool_lifecycle(self):
        registry = ToolRegistry()
        assert registry.tool_count == 0
        registry.register(DummyTool())
        assert registry.has_tool("dummy_tool")
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="integration test"))
        )
        assert result.success
        assert registry.get_execution_stats()["total_calls"] == 1
        registry.unregister("dummy_tool")
        assert not registry.has_tool("dummy_tool")

    def test_get_info_matches_registry(self):
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "dummy_tool"

    def test_get_all_descriptions_usable_by_llm(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        desc = registry.get_all_descriptions()
        assert "工具名" in desc
        assert "描述" in desc
        assert "能力" in desc
        assert "版本" in desc

    def test_search_and_execute_flow(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        found = registry.search_tools("symbolic_computation")
        assert "dummy_tool" in found
        result = asyncio.run(
            registry.execute_safe(found[0], ToolInput(query="test"))
        )
        assert result.success
