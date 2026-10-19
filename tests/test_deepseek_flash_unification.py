"""Regression coverage for the single production DeepSeek vision/text route."""

import json

from app.config.settings import MODEL_CAPABILITIES, canonical_model_name
from app.services.content_ai_provider import ContentAIProviderFactory, DeepSeekContentAIProvider
from app.services.vision_pdf_parser import VisionPDFParser
from tools.vision_tool import VisionTool


def test_legacy_model_names_are_compatibility_aliases_only():
    assert canonical_model_name("deepseek-flash") == "deepseek-flash"
    assert canonical_model_name("deepseek-v4-flash") == "deepseek-flash"
    assert canonical_model_name("qwen-vl-plus") == "deepseek-flash"
    assert MODEL_CAPABILITIES["deepseek-flash"]["vision"] is True
    assert MODEL_CAPABILITIES["deepseek-flash"]["json_output"] is True


def test_vision_tool_parses_markdown_json_without_logging_image_data():
    payload = {
        "question_text": "求极限",
        "options": [{"label": "A", "text": "1"}],
        "formulas": [],
        "figure_description": "",
        "confidence": 0.9,
        "warnings": [],
    }
    parsed = VisionTool._parse_structured_content("```json\n" + json.dumps(payload) + "\n```")
    assert parsed["status"] == "valid"
    assert parsed["value"]["question_text"] == "求极限"


def test_truncated_vision_json_is_not_marked_valid():
    parsed = VisionTool._parse_structured_content('{"question_text":"未闭合"')
    assert parsed["status"] == "invalid_or_truncated"
    assert parsed["value"] is None


def test_pdf_parser_uses_deepseek_defaults(monkeypatch):
    monkeypatch.setattr("app.services.vision_pdf_parser.settings.DEEPSEEK_API_KEY", "test-key")
    parser = VisionPDFParser()
    assert parser.model == "deepseek-flash"
    assert "deepseek.com" in parser.api_base


def test_pdf_bbox_out_of_bounds_requires_review():
    needs_review, reasons = VisionPDFParser._review_bbox(
        {"x": 0.8, "y": 0.1, "width": 0.4, "height": 0.2}
    )
    assert needs_review is True
    assert "bbox_out_of_bounds" in reasons


def test_qwen_provider_setting_cannot_activate_qwen(monkeypatch):
    monkeypatch.setattr("app.services.content_ai_provider.settings.DEEPSEEK_API_KEY", "test-key")
    provider = ContentAIProviderFactory("qwen").get_provider()
    assert isinstance(provider, DeepSeekContentAIProvider)
    assert provider.model == "deepseek-flash"
