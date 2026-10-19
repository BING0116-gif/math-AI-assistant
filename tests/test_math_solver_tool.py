import asyncio

from tools import get_registry
from tools.base_tool import ToolInput


def test_math_solver_limit_is_safe_and_deterministic():
    async def run():
        return await get_registry().execute_safe(
            "math_solver",
            ToolInput(
                query="求极限",
                parameters={
                    "type": "limit",
                    "expression": "sin(x)/x",
                    "variable": "x",
                    "point": "0",
                },
            ),
        )

    result = asyncio.run(run())
    assert result.success is True
    assert result.data["result"] == "1"
    assert "latex" in result.data


def test_math_solver_normalizes_natural_language_limit_variable_and_infinity():
    async def run():
        return await get_registry().execute_safe(
            "math_solver",
            ToolInput(
                query="求 x 趋于无穷的极限",
                parameters={
                    "type": "limit",
                    "expression": "(2*x^2+1)/(x^2-3)",
                    "variable": "x→∞",
                    "point": "∞",
                },
            ),
        )

    result = asyncio.run(run())
    assert result.success is True
    assert result.data["result"] == "2"
