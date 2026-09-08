import json
import logging

from app.observability import JsonFormatter, metrics_response, request_id_var, sanitize


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
