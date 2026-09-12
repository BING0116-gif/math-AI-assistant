"""T12：per-model 高级能力门控的确定性回归测试。"""

import pytest

from app.config.settings import MODEL_CAPABILITIES, settings
from app.services.llm_service import (
    LLMService,
    ModelCapabilityError,
    require_model_capabilities,
)
from app.services.readiness_matrix import check_ai_analysis, check_vision_ocr


def test_capability_table_contains_required_models():
    assert MODEL_CAPABILITIES["deepseek-v4-flash"] == {
        "tool_call": True,
        "json_output": True,
        "vision": False,
    }
    assert MODEL_CAPABILITIES["qwen-vl-plus"] == {
        "tool_call": False,
        "json_output": True,
        "vision": True,
    }


def test_unsupported_capability_fails_closed_before_request():
    with pytest.raises(ModelCapabilityError) as exc:
        require_model_capabilities("deepseek-v4-flash", ("vision",))

    assert exc.value.code == "MODEL_CAPABILITY_UNSUPPORTED"
    assert "vision" in str(exc.value)


def test_unknown_model_capability_fails_closed():
    with pytest.raises(ModelCapabilityError) as exc:
        require_model_capabilities("unregistered-model", ("json_output",))

    assert exc.value.code == "MODEL_CAPABILITY_UNKNOWN"


def test_vision_tool_does_not_silently_fallback_from_non_vision_model():
    from tools.vision_tool import VisionTool

    tool = VisionTool(model="deepseek-v4-flash", api_key="test-key")
    with pytest.raises(ModelCapabilityError) as exc:
        tool.recognize(("image/png", "base64"))

    assert exc.value.code == "MODEL_CAPABILITY_UNSUPPORTED"


@pytest.mark.asyncio
async def test_llm_service_rejects_unsupported_request_without_calling_provider():
    service = LLMService.__new__(LLMService)
    service.model = "qwen-vl-plus"

    class NeverCalled:
        class Chat:
            class Completions:
                async def create(self, **kwargs):  # pragma: no cover - must not run
                    raise AssertionError("provider should not be called")

            completions = Completions()

        chat = Chat()

    service._client = NeverCalled()

    with pytest.raises(ModelCapabilityError):
        await service.generate(
            "test",
            use_cache=False,
            required_capabilities=("tool_call",),
        )


@pytest.mark.asyncio
async def test_vision_provider_status_warns_for_non_vision_model(monkeypatch):
    monkeypatch.setattr(settings, "VISION_MODEL", "deepseek-v4-flash", raising=False)
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "sk-" + "v" * 30, raising=False)

    result = await check_vision_ocr()

    assert result.status == "warning"
    assert "模型能力不匹配" in result.reason
    assert result.details["model_capability"]["error_code"] == "MODEL_CAPABILITY_UNSUPPORTED"


@pytest.mark.asyncio
async def test_ai_analysis_readiness_warns_for_json_capability_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "CONTENT_AI_PROVIDER", "deepseek", raising=False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-" + "j" * 30, raising=False)
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "unregistered-model", raising=False)

    result = await check_ai_analysis()

    assert result.status == "warning"
    assert "JSON" in result.reason
    assert result.details["model_capability"]["error_code"] == "MODEL_CAPABILITY_UNKNOWN"
