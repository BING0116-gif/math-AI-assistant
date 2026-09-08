"""Capability Readiness 矩阵测试。

对应 PRD：`plans/知微_能力就绪度矩阵PRD_v1.0_2026-09-07.md`，Epic E3。

覆盖：
- FR-2 分级仅产生 ok / warning / blocker
- FR-3 非 ok 项必须给出 reason 与 remediation
- FR-4 权限守卫（401 / 403 / 200）
- FR-5 单项失败不影响整体
- FR-12 密钥脱敏：响应中绝不出现完整 key
"""

import asyncio
import json

import pytest
from starlette.requests import Request

from app.config.settings import settings
from app.services.readiness_matrix import (
    CapabilityResult,
    ReadinessMatrix,
    _key_tail,
    _summarize,
    build_readiness_matrix,
    check_ai_analysis,
    check_assessment,
    check_vision_ocr,
)

VALID_STATUS = {"ok", "warning", "blocker"}


def _request(user=None, path="/api/admin/readiness/capabilities"):
    """构造最小 Request，模拟 request.state.current_user。"""
    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "state": {}}
    req = Request(scope)
    if user is not None:
        req.state.current_user = user
        req.state.user_id = user.id
    return req


def _set(monkeypatch, name, value):
    """安全修改 settings 字段（兼容 pydantic 只读模型）。"""
    monkeypatch.setattr(settings, name, value, raising=False)


# ══════════════════════════════════════════════════════════════════
# 密钥脱敏（FR-12 / PRD 第 12 节）
# ══════════════════════════════════════════════════════════════════


def test_key_tail_returns_only_last_four():
    assert _key_tail("sk-abcdefgh1234") == "1234"
    assert _key_tail("") is None
    assert _key_tail(None) is None


@pytest.mark.asyncio
async def test_vision_ocr_details_never_leak_full_key(monkeypatch):
    """响应细节中只能出现尾号，绝不能出现完整 key。"""
    full_key = "sk-" + "x" * 40
    _set(monkeypatch, "DASHSCOPE_API_KEY", full_key)

    result = await check_vision_ocr()

    blob = json.dumps(result.details, ensure_ascii=False)
    assert full_key not in blob, "响应中泄露了完整密钥"
    assert result.details["dashscope_key"]["tail"] == full_key[-4:]
    assert result.details["dashscope_key"]["present"] is True


# ══════════════════════════════════════════════════════════════════
# 分级规则（FR-2 / FR-3）
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ai_analysis_mock_without_allow_is_blocker(monkeypatch):
    _set(monkeypatch, "CONTENT_AI_PROVIDER", "mock")
    _set(monkeypatch, "ALLOW_MOCK_PUBLISH", False)

    result = await check_ai_analysis()

    assert result.status == "blocker"
    assert result.reason and result.remediation


@pytest.mark.asyncio
async def test_ai_analysis_mock_with_allow_is_warning(monkeypatch):
    _set(monkeypatch, "CONTENT_AI_PROVIDER", "mock")
    _set(monkeypatch, "ALLOW_MOCK_PUBLISH", True)

    result = await check_ai_analysis()

    assert result.status == "warning"


@pytest.mark.asyncio
async def test_ai_analysis_missing_key_is_blocker(monkeypatch):
    _set(monkeypatch, "CONTENT_AI_PROVIDER", "deepseek")
    _set(monkeypatch, "DEEPSEEK_API_KEY", "")
    _set(monkeypatch, "DEEPSEEK_MODEL", "deepseek-v4-flash")

    result = await check_ai_analysis()

    assert result.status == "blocker"
    assert "DEEPSEEK_API_KEY" in result.reason


@pytest.mark.asyncio
async def test_ai_analysis_deprecated_model_is_warning(monkeypatch):
    _set(monkeypatch, "CONTENT_AI_PROVIDER", "deepseek")
    _set(monkeypatch, "DEEPSEEK_API_KEY", "sk-" + "y" * 30)
    _set(monkeypatch, "DEEPSEEK_MODEL", "deepseek-chat")

    result = await check_ai_analysis()

    assert result.status == "warning"
    assert "deepseek-chat" in result.reason


@pytest.mark.asyncio
async def test_vision_ocr_missing_key_is_blocker(monkeypatch):
    _set(monkeypatch, "DASHSCOPE_API_KEY", "")

    result = await check_vision_ocr()

    assert result.status == "blocker"
    assert result.reason and result.remediation


@pytest.mark.asyncio
async def test_vision_ocr_suspicious_length_is_warning(monkeypatch):
    _set(monkeypatch, "DASHSCOPE_API_KEY", "short")

    result = await check_vision_ocr()

    assert result.status == "warning"


@pytest.mark.asyncio
async def test_assessment_no_key_at_all_is_blocker(monkeypatch):
    _set(monkeypatch, "LLM_API_KEY", "")
    _set(monkeypatch, "DASHSCOPE_API_KEY", "")

    result = await check_assessment()

    assert result.status == "blocker"


@pytest.mark.asyncio
async def test_assessment_qwen_math_model_is_warning(monkeypatch):
    _set(monkeypatch, "LLM_API_KEY", "sk-" + "z" * 30)
    _set(monkeypatch, "DASHSCOPE_API_KEY", "sk-" + "z" * 30)
    _set(monkeypatch, "LLM_MATH_MODEL", "qwen-turbo")

    result = await check_assessment()

    assert result.status == "warning"
    assert "qwen" in result.reason


# ══════════════════════════════════════════════════════════════════
# 汇总（FR-7）
# ══════════════════════════════════════════════════════════════════


def test_summarize_counts_and_overall():
    capabilities = [
        CapabilityResult(id="a", name="a", status="ok"),
        CapabilityResult(id="b", name="b", status="warning"),
        CapabilityResult(id="c", name="c", status="blocker"),
    ]

    summary = _summarize(capabilities)

    assert (summary.total, summary.ok, summary.warning, summary.blocker) == (3, 1, 1, 1)
    assert summary.overall == "blocker"


def test_summarize_warning_only_overall():
    summary = _summarize([CapabilityResult(id="a", name="a", status="warning")])
    assert summary.overall == "warning"


def test_summarize_all_ok():
    summary = _summarize([CapabilityResult(id="a", name="a", status="ok")])
    assert summary.overall == "ok"


# ══════════════════════════════════════════════════════════════════
# 异常隔离与超时（FR-5 / NFR Resilience）
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_single_check_exception_is_isolated(monkeypatch):
    """某项检查抛异常时，端点仍产出结果，该项降级为 warning。"""
    import app.services.readiness_matrix as rm

    async def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(rm, "_CHECKS", [_boom])

    matrix = await rm.build_readiness_matrix()

    assert len(matrix.capabilities) == 1
    item = matrix.capabilities[0]
    assert item.status == "warning"
    assert "boom" in item.reason
    assert item.details.get("check_error")


@pytest.mark.asyncio
async def test_slow_check_degrades_to_warning(monkeypatch):
    """超时检查不得拖垮整个端点。"""
    import app.services.readiness_matrix as rm

    monkeypatch.setattr(rm, "_CHECK_TIMEOUT", 0.01)

    async def _slow():
        await asyncio.sleep(0.3)
        return CapabilityResult(id="slow", name="slow", status="ok")

    monkeypatch.setattr(rm, "_CHECKS", [_slow])

    matrix = await rm.build_readiness_matrix()

    assert matrix.capabilities[0].status == "warning"
    assert "超时" in matrix.capabilities[0].reason


@pytest.mark.asyncio
async def test_all_checks_produce_valid_status_without_external_services():
    """无外部服务时，八项检查全部降级但不抛异常。"""
    matrix = await build_readiness_matrix()

    assert len(matrix.capabilities) == 8
    for item in matrix.capabilities:
        assert item.status in VALID_STATUS
        if item.status != "ok":
            assert item.reason, f"{item.id} 非 ok 但缺少 reason"
            assert item.remediation, f"{item.id} 非 ok 但缺少 remediation"


# ══════════════════════════════════════════════════════════════════
# 权限守卫（FR-4）
# ══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_auth_returns_401():
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.readiness_api import get_capabilities

    with pytest.raises(HTTPException) as exc:
        await get_capabilities(_request(None))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_student_returns_403():
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.readiness_api import get_capabilities

    with pytest.raises(HTTPException) as exc:
        await get_capabilities(_request(SimpleNamespace(id="student", role="student")))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_returns_200_and_matrix_shape(monkeypatch):
    from types import SimpleNamespace

    import app.api.readiness_api as api_mod

    async def _fake_build():
        return ReadinessMatrix(
            generated_at="2026-09-07T00:00:00+00:00",
            summary=_summarize([]),
            capabilities=[],
        )

    monkeypatch.setattr(api_mod, "build_readiness_matrix", _fake_build)

    resp = await api_mod.get_capabilities(_request(SimpleNamespace(id="admin", role="admin")))

    assert resp.status_code == 200
    body = json.loads(resp.body.decode())
    assert body["code"] == 0
    assert "data" in body
    assert "summary" in body["data"]
    assert "capabilities" in body["data"]
