"""
Vision Tool Diagnostic Script

Comprehensive diagnosis of vision tool malfunction.
"""

import sys
import os
import traceback
from typing import Any, Dict, List

# Add project root to Python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def diagnose_vision_tool():
    """Execute comprehensive vision tool diagnosis."""
    print("=" * 60)
    print("Vision Tool Diagnostic Report")
    print("=" * 60)

    issues: List[Dict[str, Any]] = []
    checks_passed: List[str] = []

    # 1. Dependency Check
    print("\n[1] Dependency Check")
    print("-" * 40)

    import inspect
    deps_ok = True
    for pkg, import_name in [
        ("httpx", "httpx"),
        ("pydantic", "pydantic"),
        ("BaseTool", "tools.base_tool"),
        ("VisionTool", "tools.vision_tool"),
    ]:
        try:
            __import__(import_name)
            print(f"  [OK] {pkg}")
            checks_passed.append(f"Dependency: {pkg}")
        except ImportError as e:
            print(f"  [FAIL] {pkg}: {e}")
            deps_ok = False
            issues.append({
                "type": "import_error",
                "severity": "critical",
                "detail": f"Cannot import {pkg}: {e}",
            })

    # 2. BaseTool Interface Check
    print("\n[2] BaseTool Interface Check")
    print("-" * 40)

    try:
        from tools.base_tool import BaseTool, ToolInput, ToolOutput

        print(f"  BaseTool abstract class: OK")

        checks_passed.append("BaseTool interface definition OK")

    except ImportError as e:
        issues.append({
            "type": "interface_error",
            "severity": "critical",
            "detail": f"BaseTool interface import failed: {e}",
        })

    # 3. VisionTool Import Check
    print("\n[3] VisionTool Import Check")
    print("-" * 40)

    try:
        from tools.vision_tool import VisionTool, VisionToolAdapter

        print(f"  VisionTool class: OK")
        print(f"  VisionToolAdapter class: OK")

        # Check execute method signature
        execute_method = getattr(VisionToolAdapter, "execute", None)
        if execute_method:
            is_async = inspect.iscoroutinefunction(execute_method)
            print(f"  VisionToolAdapter.execute: async={is_async}")

            if not is_async:
                issues.append({
                    "type": "interface_mismatch",
                    "severity": "critical",
                    "detail": "VisionToolAdapter.execute() is NOT an async method, but BaseTool.execute() requires async",
                    "impact": "Agent call will fail due to signature mismatch",
                })

        checks_passed.append("VisionTool class import OK")

    except ImportError as e:
        issues.append({
            "type": "import_error",
            "severity": "critical",
            "detail": f"VisionTool import failed: {e}",
        })
    except Exception as e:
        issues.append({
            "type": "runtime_error",
            "severity": "critical",
            "detail": f"VisionTool check error: {e}",
        })

    # 4. ToolRegistry Registration Check
    print("\n[4] ToolRegistry Registration Check")
    print("-" * 40)

    try:
        from tools import get_registry

        registry = get_registry()
        print(f"  ToolRegistry instantiation: OK")
        print(f"  Registered tools count: {registry.tool_count}")
        print(f"  Registered tools: {registry.tool_names}")

        if registry.has_tool("vision_tool"):
            print(f"  vision_tool registration: OK")
            checks_passed.append("vision_tool is registered")

            tool = registry.get_tool("vision_tool")
            print(f"  Tool type: {type(tool).__name__}")
            print(f"  Tool version: {tool.version}")
            print(f"  Tool capabilities: {[c.value for c in tool.capabilities]}")

            if hasattr(tool, "execute"):
                is_async = inspect.iscoroutinefunction(tool.execute)
                print(f"  Tool.execute method: {'async' if is_async else 'sync'}")
        else:
            issues.append({
                "type": "not_registered",
                "severity": "high",
                "detail": "vision_tool not registered in Registry",
                "impact": "Agent cannot call vision_tool",
            })

    except Exception as e:
        issues.append({
            "type": "registry_error",
            "severity": "critical",
            "detail": f"ToolRegistry check failed: {e}",
        })

    # 5. API Key Check
    print("\n[5] API Key Check")
    print("-" * 40)

    from app.config.settings import settings
    api_key = settings.DASHSCOPE_API_KEY

    if api_key:
        print(f"  DASHSCOPE_API_KEY: OK (length: {len(api_key)})")
        checks_passed.append("API Key configured")
    else:
        print(f"  DASHSCOPE_API_KEY: NOT CONFIGURED")
        issues.append({
            "type": "config_missing",
            "severity": "high",
            "detail": "DASHSCOPE_API_KEY not configured in .env or environment variable",
            "impact": "vision_tool API call will fail",
        })

    # 6. Interface Contract Analysis
    print("\n[6] Interface Contract Analysis")
    print("-" * 40)

    try:
        from tools.base_tool import BaseTool
        from tools.vision_tool import VisionToolAdapter

        base_execute = getattr(BaseTool, "execute", None)
        adapter_execute = getattr(VisionToolAdapter, "execute", None)

        if base_execute and adapter_execute:
            base_is_async = inspect.iscoroutinefunction(base_execute)
            adapter_is_async = inspect.iscoroutinefunction(adapter_execute)

            print(f"  BaseTool.execute:   {'async' if base_is_async else 'sync'}")
            print(f"  VisionToolAdapter.execute: {'async' if adapter_is_async else 'sync'}")

            if base_is_async != adapter_is_async:
                issues.append({
                    "type": "async_mismatch",
                    "severity": "critical",
                    "detail": "async function signature mismatch",
                    "impact": "This will cause TypeError or 'coroutine was never awaited' error",
                })
            else:
                checks_passed.append("async function signature matches")

    except Exception as e:
        print(f"  Interface analysis failed: {e}")

    # 7. Tool Description Generation Check
    print("\n[7] Tool Description Generation Check")
    print("-" * 40)

    try:
        from tools.tool_description import ToolDescriptionGenerator

        registry = get_registry()
        tools = list(registry._tools.values()) if hasattr(registry, "_tools") else []

        generator = ToolDescriptionGenerator()
        descriptions = generator.generate_for_registry(tools)

        print(f"  Generated descriptions count: {len(descriptions)}")
        if descriptions:
            print(f"  Description preview:")
            for desc in descriptions[:2]:
                lines = desc.split("\n")[:3]
                for line in lines:
                    print(f"    {line}")
                print("    ...")

        checks_passed.append("Tool description generation OK")

    except Exception as e:
        issues.append({
            "type": "description_error",
            "severity": "medium",
            "detail": f"Tool description generation failed: {e}",
        })

    # Summary Report
    print("\n" + "=" * 60)
    print("Diagnostic Summary")
    print("=" * 60)

    print(f"\n[OK] Passed checks: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  - {check}")

    print(f"\n[FAIL] Issues found: {len(issues)}")
    for i, issue in enumerate(issues, 1):
        print(f"\n  [{i}] {issue['type'].upper()} ({issue['severity']})")
        print(f"      Detail: {issue['detail']}")
        if "impact" in issue:
            print(f"      Impact: {issue['impact']}")

    # Root Cause Analysis
    print("\n" + "=" * 60)
    print("Root Cause Analysis")
    print("=" * 60)

    critical_issues = [i for i in issues if i["severity"] == "critical"]

    if critical_issues:
        print("\n[CRITICAL] Critical issues found:")
        for issue in critical_issues:
            print(f"\n  - {issue['detail']}")

        async_issues = [i for i in critical_issues if "async" in i["type"]]
        if async_issues:
            print("\n[ROOT CAUSE] The main issue: VisionToolAdapter.execute() is a synchronous method,")
            print("             but BaseTool.execute() abstract method requires an async method.")
            print("             This causes signature mismatch when ToolRegistry.execute_safe() is called.")

    return issues


if __name__ == "__main__":
    print("Starting Vision Tool diagnostics...\n")

    import inspect
    issues = diagnose_vision_tool()

    if any(i["severity"] == "critical" for i in issues):
        print("\n\n[SUGGESTED FIX]")
        print("  1. Change VisionToolAdapter.execute() to async method")
        print("  2. Call sync self._vision_tool.recognize() inside the async method")
        print("  3. Add proper error handling and logging")
        sys.exit(1)
    else:
        print("\n\n[RESULT] No critical issues found")
        sys.exit(0)
