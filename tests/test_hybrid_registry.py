"""
HybridToolRegistry 迁移测试套件。

覆盖范围：
1. HybridToolRegistry 注册与生命周期管理
2. 双模式注册（自定义 + LangChain）
3. 完全向后兼容性验证（原有 ToolRegistry API 全部可用）
4. 安全执行与统计功能
5. LangChain 工具转换与获取
6. 边界情况与错误处理
7. ToolInvoker 与 HybridToolRegistry 集成
"""

import pytest
import asyncio
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.hybrid_registry import (
    HybridToolRegistry,
    ToolNotFoundError,
    ToolExecutionError,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class DummyTool(BaseTool):
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
    name = "failing_tool"
    description = "校验失败的测试工具"
    version = "1.0.0"
    capabilities = [ToolCapability.NUMERICAL_COMPUTATION]

    def validate_input(self, input_data: ToolInput) -> Optional[str]:
        return "This tool always fails validation"

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        return ToolOutput(success=True, result="x", tool_name=self.name)


class ExceptionTool(BaseTool):
    name = "exception_tool"
    description = "执行时抛异常的测试工具"
    version = "1.0.0"
    capabilities = [ToolCapability.PLOTTING]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        raise RuntimeError("Test exception")


# ---------------------------------------------------------------------------
# 1. 注册与生命周期管理
# ---------------------------------------------------------------------------

class TestHybridRegistryRegister:
    def test_register_increases_count(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        assert registry.tool_count == 1

    def test_register_multiple_tools(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="tool_a"))
        registry.register(DummyTool(tool_name="tool_b"))
        assert registry.tool_count == 2

    def test_empty_name_raises(self):
        registry = HybridToolRegistry()
        tool = DummyTool()
        tool.name = ""
        with pytest.raises(ValueError, match="name 属性不能为空"):
            registry.register(tool)

    def test_duplicate_overwrites_with_warning(self, caplog):
        registry = HybridToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool()
        t2.version = "2.0.0"
        registry.register(t1)
        with caplog.at_level("WARNING"):
            registry.register(t2)
        assert "将被覆盖为 v2.0.0" in caplog.text
        assert registry.tool_count == 1
        assert registry.get_tool("dummy_tool").version == "2.0.0"

    def test_registration_maintains_both_stores(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        assert registry.tool_count == 1
        custom_tools = registry.get_all_tools()
        assert len(custom_tools) == 1
        assert custom_tools[0].name == "dummy_tool"


class TestHybridRegistryUnregister:
    def test_unregister_existing(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        assert registry.unregister("dummy_tool") is True
        assert registry.tool_count == 0

    def test_unregister_nonexistent(self):
        registry = HybridToolRegistry()
        assert registry.unregister("nonexistent") is False

    def test_unregister_decreases_count(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="tool_a"))
        registry.register(DummyTool(tool_name="tool_b"))
        assert registry.tool_count == 2
        registry.unregister("tool_a")
        assert registry.tool_count == 1

    def test_unregister_clears_langchain_store(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        registry.unregister("dummy_tool")
        assert registry.langchain_tool_count == 0


# ---------------------------------------------------------------------------
# 2. 工具发现接口
# ---------------------------------------------------------------------------

class TestHybridRegistryGetTool:
    def test_get_existing_tool(self):
        registry = HybridToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        assert registry.get_tool("dummy_tool") is tool

    def test_get_nonexistent_raises(self):
        registry = HybridToolRegistry()
        with pytest.raises(ToolNotFoundError, match="工具未注册"):
            registry.get_tool("nonexistent")


class TestHybridRegistryHasTool:
    def test_has_registered_tool(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        assert registry.has_tool("dummy_tool") is True

    def test_does_not_have_unregistered_tool(self):
        registry = HybridToolRegistry()
        assert registry.has_tool("dummy_tool") is False


class TestHybridRegistrySearchTools:
    def test_search_by_matching_capability(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("symbolic_computation")
        assert "dummy_tool" in result

    def test_search_by_nonmatching_capability(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("plotting")
        assert "dummy_tool" not in result

    def test_search_empty_registry(self):
        registry = HybridToolRegistry()
        assert registry.search_tools("symbolic_computation") == []

    def test_search_case_sensitive(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = registry.search_tools("SYMBOLIC_COMPUTATION")
        assert "dummy_tool" not in result

    def test_search_multiple_capability_match(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="tool_a"))
        registry.register(DummyTool(tool_name="tool_b"))
        result = registry.search_tools("verification")
        assert "tool_a" in result
        assert "tool_b" in result


class TestHybridRegistryListTools:
    def test_list_returns_all_tools(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="tool_x"))
        registry.register(DummyTool(tool_name="tool_y"))
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_list_empty_registry(self):
        registry = HybridToolRegistry()
        assert registry.list_tools() == []


class TestHybridRegistryGetAllDescriptions:
    def test_returns_formatted_descriptions(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        desc = registry.get_all_descriptions()
        assert "当前可用工具列表" in desc
        assert "dummy_tool" in desc

    def test_empty_registry_returns_message(self):
        registry = HybridToolRegistry()
        assert registry.get_all_descriptions() == "当前无可用工具。"

    def test_multiple_tools_all_included(self):
        registry = HybridToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool(tool_name="another_tool")
        registry.register(t1)
        registry.register(t2)
        desc = registry.get_all_descriptions()
        assert "dummy_tool" in desc
        assert "another_tool" in desc


class TestHybridRegistryGetToolsByNames:
    def test_returns_only_existing_tools(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        tools = registry.get_tools_by_names(["dummy_tool", "nonexistent"])
        assert len(tools) == 1
        assert tools[0].name == "dummy_tool"

    def test_empty_list_returns_empty(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        tools = registry.get_tools_by_names([])
        assert tools == []

    def test_skips_nonexistent_with_warning(self, caplog):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        with caplog.at_level("WARNING"):
            registry.get_tools_by_names(["nonexistent"])
        assert "已跳过" in caplog.text


class TestHybridRegistryToolNames:
    def test_returns_all_registered_names(self):
        registry = HybridToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool(tool_name="tool_b")
        registry.register(t1)
        registry.register(t2)
        names = registry.tool_names
        assert "dummy_tool" in names
        assert "tool_b" in names

    def test_empty_registry_returns_empty_list(self):
        registry = HybridToolRegistry()
        assert registry.tool_names == []


# ---------------------------------------------------------------------------
# 3. 安全执行接口
# ---------------------------------------------------------------------------

class TestHybridRegistryExecuteSafe:
    def test_execute_success(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test query"))
        )
        assert result.success is True
        assert "processed: test query" in result.result

    def test_execute_tool_not_found(self):
        registry = HybridToolRegistry()
        result = asyncio.run(
            registry.execute_safe("nonexistent", ToolInput(query="test"))
        )
        assert result.success is False
        assert "工具未注册" in result.error

    def test_execute_validation_fails(self):
        registry = HybridToolRegistry()
        registry.register(FailingTool())
        result = asyncio.run(
            registry.execute_safe("failing_tool", ToolInput(query="anything"))
        )
        assert result.success is False
        assert "输入校验失败" in result.error

    def test_execute_exception_returns_tool_output(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(fail_on_execute=True))
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test"))
        )
        assert result.success is False
        assert "RuntimeError" in result.error

    def test_execution_time_recorded(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="test"))
        )
        assert result.execution_time_ms >= 0
        assert result.tool_name == "dummy_tool"

    def test_multiple_calls_update_stats(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2
        assert stats["success_count"] == 2

    def test_execute_with_context_params(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        result = asyncio.run(
            registry.execute_safe(
                "dummy_tool",
                ToolInput(query="test", parameters={"option": "fast"},
                          context={"user_id": "u1"})
            )
        )
        assert result.success is True

    def test_execute_exception_tool(self):
        registry = HybridToolRegistry()
        registry.register(ExceptionTool())
        result = asyncio.run(
            registry.execute_safe("exception_tool", ToolInput(query="fail"))
        )
        assert result.success is False
        assert "RuntimeError" in result.error


# ---------------------------------------------------------------------------
# 4. 执行统计与监控
# ---------------------------------------------------------------------------

class TestHybridRegistryExecutionStats:
    def test_empty_registry_stats(self):
        registry = HybridToolRegistry()
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 0.0

    def test_stats_after_successful_calls(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 1.0

    def test_stats_mixed_success_failure(self):
        registry = HybridToolRegistry()
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
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="a")))
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="b")))
        stats = registry.get_execution_stats()
        assert "dummy_tool" in stats["tool_stats"]
        assert stats["tool_stats"]["dummy_tool"]["calls"] == 2
        assert stats["tool_stats"]["dummy_tool"]["successes"] == 2

    def test_history_max_size_enforced(self):
        registry = HybridToolRegistry()
        registry._max_history = 5
        registry.register(DummyTool())
        for i in range(10):
            asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query=f"q{i}")))
        assert len(registry._execution_history) == 5


# ---------------------------------------------------------------------------
# 5. 混合统计 (Hybrid Stats)
# ---------------------------------------------------------------------------

class TestHybridRegistryStats:
    def test_hybrid_stats_empty(self):
        registry = HybridToolRegistry()
        stats = registry.get_hybrid_stats()
        assert stats["custom_tool_count"] == 0
        assert "langchain_enabled" in stats
        assert "fully_synced" in stats

    def test_hybrid_stats_with_tools(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="t1"))
        registry.register(DummyTool(tool_name="t2"))
        stats = registry.get_hybrid_stats()
        assert stats["custom_tool_count"] == 2
        assert "t1" in stats["tool_names"]
        assert "t2" in stats["tool_names"]

    def test_execute_and_check_hybrid_stats(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        asyncio.run(registry.execute_safe("dummy_tool", ToolInput(query="test")))
        stats = registry.get_hybrid_stats()
        exec_stats = stats["execution_stats"]
        assert exec_stats["total_calls"] == 1
        assert exec_stats["success_rate"] == 1.0


# ---------------------------------------------------------------------------
# 6. LangChain 双模式测试
# ---------------------------------------------------------------------------

class TestHybridRegistryLangChain:
    def test_langchain_enabled_flag(self):
        registry = HybridToolRegistry()
        assert isinstance(registry.langchain_enabled, bool)

    def test_get_langchain_tools_returns_list(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        lc_tools = registry.get_langchain_tools()
        assert isinstance(lc_tools, list)

    def test_langchain_tool_count_matches(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool(tool_name="t_a"))
        registry.register(DummyTool(tool_name="t_b"))
        lc_tools = registry.get_langchain_tools()
        if registry.langchain_enabled:
            assert registry.langchain_tool_count == 2
            assert len(lc_tools) == 2
        else:
            assert registry.langchain_tool_count == 0
            assert len(lc_tools) == 0

    def test_langchain_tool_has_name(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        lc_tools = registry.get_langchain_tools()
        if lc_tools:
            assert lc_tools[0].name == "dummy_tool"

    def test_langchain_tool_not_found_raises(self):
        registry = HybridToolRegistry()
        if registry.langchain_enabled:
            with pytest.raises(ToolNotFoundError):
                registry.get_langchain_tool("nonexistent")

    def test_refresh_langchain_tools(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        prev_count = registry.langchain_tool_count
        registry.refresh_langchain_tools()
        assert registry.langchain_tool_count == prev_count

    def test_unregister_removes_langchain_tool(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        registry.unregister("dummy_tool")
        assert registry.langchain_tool_count == 0


# ---------------------------------------------------------------------------
# 7. 向后兼容性测试
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_tools_package_alias_is_hybrid(self):
        from tools import ToolRegistry as PkgToolRegistry
        assert PkgToolRegistry is HybridToolRegistry

    def test_old_name_still_works(self):
        from tools import ToolRegistry as TR
        registry = TR()
        registry.register(DummyTool())
        assert registry.has_tool("dummy_tool")
        assert registry.tool_count == 1

    def test_hybrid_is_usable_via_legacy_import(self):
        registry = HybridToolRegistry()
        from tools import ToolRegistry as PkgToolRegistry
        assert isinstance(registry, PkgToolRegistry)

    def test_all_original_apis_available(self):
        registry = HybridToolRegistry()
        original_apis = [
            "register", "unregister", "get_tool", "has_tool",
            "search_tools", "list_tools", "get_all_descriptions",
            "get_tools_by_names", "get_all_tools", "execute_safe",
            "get_execution_stats", "tool_count", "tool_names",
        ]
        for api in original_apis:
            assert hasattr(registry, api), f"缺少API: {api}"

    def test_all_new_apis_available(self):
        registry = HybridToolRegistry()
        new_apis = [
            "get_langchain_tool", "get_langchain_tools",
            "refresh_langchain_tools", "get_hybrid_stats",
            "langchain_enabled", "langchain_tool_count",
        ]
        for api in new_apis:
            assert hasattr(registry, api), f"缺少新API: {api}"

    def test_legacy_class_still_functional(self):
        from tools import ToolRegistry as TR
        legacy = TR()
        legacy.register(DummyTool())
        assert legacy.has_tool("dummy_tool")
        result = asyncio.run(
            legacy.execute_safe("dummy_tool", ToolInput(query="compat"))
        )
        assert result.success is True

    def test_hybrid_has_same_behavior_as_legacy(self):
        from tools import ToolRegistry as TR
        hybrid = HybridToolRegistry()
        legacy = TR()
        hybrid.register(DummyTool())
        legacy.register(DummyTool())
        assert hybrid.tool_count == legacy.tool_count
        assert hybrid.tool_names == legacy.tool_names


# ---------------------------------------------------------------------------
# 8. 异常类测试
# ---------------------------------------------------------------------------

class TestExceptionClasses:
    def test_tool_not_found_error(self):
        error = ToolNotFoundError("test_tool")
        assert "工具未注册" in str(error)
        assert error.tool_name == "test_tool"

    def test_tool_execution_error(self):
        error = ToolExecutionError("test_tool", "something went wrong")
        assert "test_tool" in str(error)
        assert "something went wrong" in str(error)
        assert error.tool_name == "test_tool"


# ---------------------------------------------------------------------------
# 9. ToolInvoker 与 HybridToolRegistry 集成测试
# ---------------------------------------------------------------------------

class TestToolInvokerWithHybridRegistry:
    def test_invoker_accepts_hybrid_registry(self):
        from tools.tool_invoker import ToolInvoker
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        invoker = ToolInvoker(registry)
        assert invoker.registry is registry

    def test_invoker_accepts_tool_registry_alias(self):
        from tools import ToolRegistry as TR
        from tools.tool_invoker import ToolInvoker
        registry = TR()
        registry.register(DummyTool())
        invoker = ToolInvoker(registry)
        assert invoker.registry is registry

    def test_invoker_invoke_with_hybrid(self):
        from tools.tool_invoker import ToolInvoker
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        invoker = ToolInvoker(registry)
        result = asyncio.run(
            invoker.invoke("dummy_tool", ToolInput(query="hello"))
        )
        assert result.success is True

    def test_invoker_format_result(self):
        from tools.tool_invoker import ToolInvoker
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        invoker = ToolInvoker(registry)
        result = asyncio.run(
            invoker.invoke("dummy_tool", ToolInput(query="hello"))
        )
        formatted = invoker.format_result_for_llm(result)
        assert "processed: hello" in formatted


# ---------------------------------------------------------------------------
# 10. 全局单例与包导入测试
# ---------------------------------------------------------------------------

class TestGlobalRegistrySingleton:
    def test_get_registry_returns_hybrid(self):
        from tools import get_registry, init_registry
        init_registry(None)
        registry = get_registry()
        assert isinstance(registry, HybridToolRegistry)

    def test_get_registry_is_singleton(self):
        from tools import get_registry, init_registry
        init_registry(None)
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_init_registry_custom_instance(self):
        from tools import get_registry, init_registry
        custom = HybridToolRegistry()
        init_registry(custom)
        assert get_registry() is custom

    def test_tools_init_exports(self):
        from tools import HybridToolRegistry, ToolRegistry, ToolNotFoundError
        from tools import BaseTool, ToolInput, ToolOutput, ToolCapability
        from tools import get_registry, init_registry
        assert HybridToolRegistry is not None
        assert ToolRegistry is not None
        assert ToolNotFoundError is not None
        assert get_registry is not None
        assert init_registry is not None


# ---------------------------------------------------------------------------
# 11. 完整生命周期集成测试
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    def test_full_tool_lifecycle(self):
        registry = HybridToolRegistry()
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
        registry = HybridToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "dummy_tool"

    def test_get_all_descriptions_usable_by_llm(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        desc = registry.get_all_descriptions()
        assert "工具名" in desc
        assert "描述" in desc
        assert "能力" in desc
        assert "版本" in desc

    def test_search_and_execute_flow(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        found = registry.search_tools("symbolic_computation")
        assert "dummy_tool" in found
        result = asyncio.run(
            registry.execute_safe(found[0], ToolInput(query="test"))
        )
        assert result.success

    def test_multiple_register_unregister_cycle(self):
        registry = HybridToolRegistry()
        for i in range(5):
            tool = DummyTool(tool_name=f"tool_{i}")
            registry.register(tool)
        assert registry.tool_count == 5
        for i in range(3):
            registry.unregister(f"tool_{i}")
        assert registry.tool_count == 2
        remaining = registry.tool_names
        assert "tool_3" in remaining
        assert "tool_4" in remaining

    def test_exception_tool_does_not_crash_registry(self):
        registry = HybridToolRegistry()
        registry.register(DummyTool())
        registry.register(ExceptionTool())
        r1 = asyncio.run(
            registry.execute_safe("dummy_tool", ToolInput(query="ok"))
        )
        r2 = asyncio.run(
            registry.execute_safe("exception_tool", ToolInput(query="fail"))
        )
        assert r1.success is True
        assert r2.success is False
        stats = registry.get_execution_stats()
        assert stats["total_calls"] == 2