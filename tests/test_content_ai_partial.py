"""T14：Content AI 不完整结果必须显式标记 partial。"""

import json
from types import SimpleNamespace

from app.models.content_ai import ContentAIAnalysisResult, ContentAIVerificationResult
from app.services.content_ai_analysis import (
    _compute_gate,
    _mark_partial_result,
    _serialize_run,
)
from app.services.content_ai_provider import (
    PARTIAL_REASON_PARSE_RECOVERED,
    PARTIAL_REASON_TRUNCATED,
    DeepSeekContentAIProvider,
    _ContentAIChatResponse,
)


def _snapshot() -> dict:
    return {
        "candidate_id": "candidate-t14",
        "detected_question_type": "choice",
        "stem": "1+1=?",
        "options": [{"id": "A", "text": "2"}, {"id": "B", "text": "3"}],
        "original_answer": "A",
        "original_solution": "2",
        "suggested_knowledge_point_codes": [],
    }


def _model_payload(*, confidence: float = 0.95) -> dict:
    return {
        "question_type": "choice",
        "knowledge_point_codes": [],
        "difficulty": 1,
        "analysis": "1+1=2",
        "common_mistakes": [],
        "answer_check": {
            "official_answer": "A",
            "consistent": True,
            "reason": "一致",
        },
        "confidence": confidence,
        "flags": [],
        "verification": {
            "verdict": "pass",
            "answer_consistent": True,
            "analysis_correct": True,
            "kp_valid": True,
            "answer_spec_valid": True,
            "issues": [],
            "confidence": confidence,
        },
    }


def test_truncated_response_after_retry_is_partial(monkeypatch):
    provider = DeepSeekContentAIProvider(api_key="sk-test")
    raw = json.dumps(_model_payload(), ensure_ascii=False)
    calls = []

    def fake_chat(_prompt, _temperature):
        calls.append(1)
        return _ContentAIChatResponse(raw, finish_reason="length")

    monkeypatch.setattr(provider, "_chat", fake_chat)

    analysis, verifier = provider.analyze_and_verify(_snapshot(), {})

    assert len(calls) == 2
    assert analysis.partial is True
    assert verifier.partial is True
    assert PARTIAL_REASON_TRUNCATED in analysis.partial_reasons


def test_bracket_recovery_never_becomes_complete(monkeypatch):
    provider = DeepSeekContentAIProvider(api_key="sk-test")
    truncated = json.dumps(_model_payload(), ensure_ascii=False)[:-1]
    calls = []

    def fake_chat(_prompt, _temperature):
        calls.append(1)
        return _ContentAIChatResponse(truncated, finish_reason="length")

    monkeypatch.setattr(provider, "_chat", fake_chat)

    analysis, verifier = provider.analyze_and_verify(_snapshot(), {})

    assert len(calls) == 2
    assert analysis.analysis == "1+1=2"
    assert analysis.partial is True
    assert verifier.partial is True
    assert PARTIAL_REASON_PARSE_RECOVERED in analysis.partial_reasons
    assert PARTIAL_REASON_TRUNCATED in analysis.partial_reasons


def test_low_confidence_is_partial_and_cannot_pass_gate():
    analysis = ContentAIAnalysisResult(confidence=0.69)
    verifier = ContentAIVerificationResult(confidence=0.95)
    provider = SimpleNamespace(is_available=lambda: True)

    reasons = _mark_partial_result(analysis, verifier, provider)
    status, gate, gate_reasons = _compute_gate(analysis, verifier)

    assert reasons == ["analysis_confidence_below_threshold"]
    assert analysis.partial is True
    assert verifier.partial is True
    assert (status, gate) == ("doubtful", "DOUBTFUL")
    assert "[partial] analysis_confidence_below_threshold" in gate_reasons


def test_provider_abnormal_result_is_partial_and_serialized_for_api():
    analysis = ContentAIAnalysisResult()
    verifier = ContentAIVerificationResult()
    provider = SimpleNamespace(is_available=lambda: False)

    _mark_partial_result(analysis, verifier, provider)
    run = SimpleNamespace(
        id="run-1",
        candidate_id="candidate-1",
        provider="degraded-provider",
        model="model-1",
        prompt_version="v1",
        status="doubtful",
        gate="DOUBTFUL",
        analysis_json=analysis.model_dump(),
        verifier_json=verifier.model_dump(),
        gate_reasons=[],
        attempt_no=1,
        parent_run_id=None,
        human_disposition=None,
        human_note=None,
        error_code=None,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=None,
        updated_at=None,
    )

    payload = _serialize_run(run)

    assert payload["partial"] is True
    assert payload["partial_reasons"] == ["provider_status_abnormal"]
