from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")


def test_agent_alert_rules_are_deployable_shape():
    root = Path(__file__).parents[1]
    config = yaml.safe_load((root / "ops" / "prometheus.yml").read_text(encoding="utf-8"))
    rules = yaml.safe_load((root / "ops" / "prometheus-agent-alerts.yml").read_text(encoding="utf-8"))

    assert "/etc/prometheus/agent-alerts.yml" in config["rule_files"]
    group = rules["groups"][0]
    assert group["name"] == "math-ai-agent-runtime"
    alerts = {item["alert"]: item for item in group["rules"]}
    assert set(alerts) == {
        "MathAIAgentFailureRateHigh",
        "MathAIAgentToolErrorRateHigh",
        "MathAIAgentTimeToFirstTokenHigh",
        "MathAIAgentContextTrimRateHigh",
        "MathAIAgentMetricsMissing",
    }
    for alert in alerts.values():
        assert alert["expr"]
        assert alert["for"]
        assert alert["labels"]["service"] == "math-ai-assistant"
