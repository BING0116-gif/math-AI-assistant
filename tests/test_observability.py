import json
import logging

from app.config.settings import Settings
from app.observability import (
    AGENT_ANSWER_MODIFIED,
    AGENT_CRITIC_VERDICTS,
    AGENT_FOLLOWUP,
    AGENT_REVIEW_SAMPLED,
    AGENT_REVIEW_VERDICTS,
    MODEL_ROUTE,
    TOOL_CIRCUIT_STATE,
    JsonFormatter,
    metrics_response,
    request_id_var,
    sanitize,
)


def test_sanitize_redacts_sensitive_nested_fields():
    result = sanitize({"authorization": "Bearer secret", "nested": {"api_key": "x", "safe": 3}})
    assert result == {"authorization": "[REDACTED]", "nested": {"api_key": "[REDACTED]", "safe": 3}}


def test_json_formatter_carries_request_id_without_sensitive_extra():
    token = request_id_var.set("req-test")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "req-test"
        assert payload["message"] == "hello"
    finally:
        request_id_var.reset(token)


def test_metrics_response_is_prometheus_text():
    response = metrics_response()
    assert response.status_code == 200
    assert b"mathai_http_requests_total" in response.body


def test_quality_loop_metrics_are_registered_with_documented_labels():
    expected = {
        AGENT_CRITIC_VERDICTS: ("verdict", "capability"),
        AGENT_ANSWER_MODIFIED: ("source",),
        AGENT_FOLLOWUP: ("gap",),
        AGENT_REVIEW_SAMPLED: ("queue",),
        AGENT_REVIEW_VERDICTS: ("verdict", "reviewer_type"),
        MODEL_ROUTE: ("from", "to", "reason"),
        TOOL_CIRCUIT_STATE: ("tool", "state"),
    }
    for metric, labels in expected.items():
        assert tuple(metric._labelnames) == labels

    payload = metrics_response().body
    for name in (
        b"mathai_agent_critic_verdicts_total",
        b"mathai_agent_answer_modified_total",
        b"mathai_agent_followup_total",
        b"mathai_agent_review_sampled_total",
        b"mathai_agent_review_verdicts_total",
        b"mathai_model_route_total",
        b"mathai_tool_circuit_state",
    ):
        assert name in payload


def test_quality_metrics_flag_defaults_to_enabled_without_reading_dotenv():
    assert Settings(_env_file=None).QUALITY_METRICS_ENABLED is True
