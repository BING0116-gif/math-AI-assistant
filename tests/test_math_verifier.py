"""T05 MathVerifier 的确定性回归测试。"""

import logging
from unittest.mock import Mock

import pytest

from app.services.math_verifier import (
    FAILED,
    INCONCLUSIVE,
    VERIFIED,
    MathVerifier,
    verify_draft_with_single_retry,
)
from agent_core.langchain_adapter import LangChainToolConverter
from tools import get_registry, init_registry
from tools.hybrid_registry import HybridToolRegistry
from tools.math_verify_tool import MathVerifyTool
from tools.base_tool import ToolInput


@pytest.fixture
def verifier():
    return MathVerifier()


def test_wrong_but_fluent_root_is_blocked(verifier):
    request = {"type": "equation", "equation": "x**2 - 5*x + 6 = 0", "variable": "x", "solutions": [2, 4]}
    result = verifier.verify(request)
    assert result.status == FAILED
    assert result.safe_to_publish is False
    assert [check.passed for check in result.checks] == [True, False]


@pytest.mark.parametrize(
    ("case", "expected_status"),
    [
        ({"type": "system", "equations": ["x+y=3", "x-y=1"], "variables": ["x", "y"], "solution": {"x": 2, "y": 1}}, VERIFIED),
        ({"type": "derivative", "expression": "sin(x)*x**2", "derivative": "2*x*sin(x)+x**2*cos(x)", "variable": "x"}, VERIFIED),
        ({"type": "integral", "expression": "x**2", "variable": "x", "lower": 0, "upper": 3, "claimed": 9}, VERIFIED),
        ({"type": "limit", "expression": "sin(x)/x", "variable": "x", "point": 0, "claimed": 1}, VERIFIED),
        ({"type": "function_value", "expression": "x**2+y", "values": {"x": 3, "y": 2}, "claimed": 11}, VERIFIED),
        ({"type": "matrix", "operation": "multiply", "operands": [[[1, 2]], [[3], [4]]], "claimed": [[11]]}, VERIFIED),
        ({"type": "probability", "favorable": 3, "total": 8, "claimed": "3/8"}, VERIFIED),
    ],
)
def test_deterministic_supported_fixtures(verifier, case, expected_status):
    assert verifier.verify(case).status == expected_status


def test_unsupported_or_malformed_is_inconclusive_not_verified(verifier):
    unsupported = verifier.verify({"type": "geometry_proof", "claimed": "AB=CD"})
    malformed = verifier.verify({"type": "equation", "equation": "x=__import__('os')", "solution": 1})
    assert unsupported.status == INCONCLUSIVE
    assert malformed.status == INCONCLUSIVE
    assert unsupported.safe_to_publish is True
    assert malformed.safe_to_publish is True


def test_improper_integral_is_not_false_verified(verifier):
    result = verifier.verify(
        {"type": "integral", "expression": "1/x", "variable": "x", "lower": -1, "upper": 1, "claimed": 0}
    )
    assert result.status == INCONCLUSIVE
    assert result.checks[0].type == "boundary"


def test_mock_mode_fixture_is_deterministic(monkeypatch, verifier):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "CONTENT_AI_PROVIDER", "mock")
    case = {"type": "function_value", "expression": "2*x+1", "values": {"x": 5}, "claimed": 11}
    assert verifier.verify(case).to_dict() == verifier.verify(case).to_dict()


def test_verifier_exception_is_isolated_and_warned(caplog):
    verifier = MathVerifier()
    verifier._verify = Mock(side_effect=RuntimeError("boom"))
    with caplog.at_level(logging.WARNING):
        result = verifier.verify({"type": "equation", "equation": "x=1", "solution": 1})
    assert result.status == INCONCLUSIVE
    assert result.warning == "未完全验证"
    assert "RuntimeError" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.asyncio
async def test_failed_verification_redrafts_at_most_once():
    calls = 0

    async def redraft(draft, request, result):
        nonlocal calls
        calls += 1
        return "重新推导：x=2 或 x=3", {**request, "solutions": [2, 3]}

    result = await verify_draft_with_single_retry(
        "解释很流畅，但误写 x=2 或 x=4",
        {"type": "equation", "equation": "x**2-5*x+6=0", "variable": "x", "solutions": [2, 4]},
        redraft=redraft,
    )
    assert calls == 1
    assert result.retry_count == 1
    assert result.verification.status == VERIFIED


@pytest.mark.asyncio
async def test_second_failure_does_not_loop():
    redraft = Mock(return_value=("仍然错误", {"type": "equation", "equation": "x=1", "solution": 2}))
    result = await verify_draft_with_single_retry(
        "错误草稿",
        {"type": "equation", "equation": "x=1", "solution": 2},
        redraft=redraft,
    )
    assert redraft.call_count == 1
    assert result.retry_count == 1
    assert result.verification.status == FAILED
    assert result.verification.safe_to_publish is False


@pytest.mark.asyncio
async def test_inconclusive_publication_has_explicit_notice(verifier):
    result = await verify_draft_with_single_retry(
        "暂定答案",
        {"type": "unsupported"},
        verifier=verifier,
    )
    assert result.verification.status == INCONCLUSIVE
    assert "未能被程序完全验证" in result.publication_text


@pytest.mark.asyncio
async def test_math_verify_tool_returns_unified_structure():
    output = await MathVerifyTool().execute(
        ToolInput(
            query="验证函数值",
            parameters={"type": "function_value", "expression": "x+1", "values": {"x": 2}, "claimed": 3},
        )
    )
    assert output.success is True
    assert output.data["status"] == VERIFIED
    assert set(output.data) >= {"status", "checks", "confidence", "safe_to_publish"}


@pytest.mark.asyncio
async def test_langchain_adapter_passes_structured_verification_request():
    tool = LangChainToolConverter().convert(MathVerifyTool())
    output = await tool.ainvoke(
        {
            "query": "验证根",
            "parameters": {"type": "equation", "equation": "x**2=4", "variable": "x", "solutions": [-2, 2]},
        }
    )
    assert '"status": "verified"' in output


def test_builtin_registry_exposes_math_verify():
    init_registry(HybridToolRegistry())
    # get_registry only returns the explicitly injected empty registry; verify built-ins via fresh global setup.
    import tools
    tools._registry = None
    try:
        assert get_registry().get_tool("math_verify").name == "math_verify"
    finally:
        tools._registry = None
