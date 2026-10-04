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
        # 阶段二可靠性告警（路线图 4.7）
        "MathAIAgentToolTimeoutRateHigh",
        "MathAIToolCircuitOpen",
        "MathAIAgentTimeoutRateHigh",
        "MathAIDegradationRateHigh",
        "MathAIModelFailoverFrequent",
        "MathAISSEHeartbeatMissing",
    }
    for alert in alerts.values():
        assert alert["expr"]
        assert alert["for"]
        assert alert["labels"]["service"] == "math-ai-assistant"

    # 可运维性 DoD：可靠性 P1 告警必须在 runbook 有对应处置段。
    runbook = (root / "ops" / "agent-observability-runbook.md").read_text(encoding="utf-8")
    for alert_name in (
        "MathAIAgentToolTimeoutRateHigh",
        "MathAIToolCircuitOpen",
        "MathAIAgentTimeoutRateHigh",
        "MathAIDegradationRateHigh",
    ):
        assert alert_name in runbook, f"runbook 缺少 {alert_name} 处置段"
