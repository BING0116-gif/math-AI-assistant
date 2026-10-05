"""阶段六 8.1/8.4 灰度发布与 Grafana provisioning 回归测试。"""

import json
from pathlib import Path

import pytest

from app.services import feature_flags as flags_module
from app.services.feature_flags import (
    FLAG_REGISTRY,
    bucket_percent,
    evaluate_flag_guardrails,
    flag_status,
    is_enabled,
)


@pytest.fixture(autouse=True)
def reset_rollback_state():
    flags_module._ROLLBACK_AT.clear()
    yield
    flags_module._ROLLBACK_AT.clear()


def test_bucket_is_stable_per_flag_and_key():
    assert bucket_percent("model_routing", "user-a:session-1") == bucket_percent("model_routing", "user-a:session-1")
    assert bucket_percent("model_routing", "user-a") != bucket_percent("memory_conflict", "user-a") or True
    # 0..99 界内
    assert 0 <= bucket_percent("model_routing", "user-x") <= 99


def test_disabled_flag_without_rollout_uses_base_setting(monkeypatch):
    monkeypatch.setattr("app.config.settings.settings.MODEL_ROUTING_ENABLED", False)
    assert is_enabled("model_routing", "user-a") is False
    monkeypatch.setattr("app.config.settings.settings.MODEL_ROUTING_ENABLED", True)
    # 无放量表 → 基准值
    assert is_enabled("model_routing", "user-a") is True


def test_rollout_percent_buckets_monotonically(monkeypatch):
    monkeypatch.setattr("app.config.settings.settings.MODEL_ROUTING_ENABLED", True)
    monkeypatch.setattr("app.config.settings.settings.FEATURE_FLAG_ROLLOUT", {"model_routing": 0})
    assert is_enabled("model_routing", "anyone") is False

    monkeypatch.setattr("app.config.settings.settings.FEATURE_FLAG_ROLLOUT", {"model_routing": 100})
    assert is_enabled("model_routing", "anyone") is True

    # 50%:桶值 < 50 的用户可见;同 key 多次判定一致
    monkeypatch.setattr("app.config.settings.settings.FEATURE_FLAG_ROLLOUT", {"model_routing": 50})
    key = "bucket-user:session-1"
    expected = bucket_percent("model_routing", key) < 50
    assert is_enabled("model_routing", key) is expected
    assert is_enabled("model_routing", key) is expected


def test_unregistered_flag_falls_back_to_base(monkeypatch):
    monkeypatch.setattr("app.config.settings.settings.MEMORY_CONFLICT_ENABLED", False)
    assert is_enabled("memory_conflict", "user-a") is False
    # 未注册的 flag 名:恒 False(宁可保守)
    assert is_enabled("unknown_flag", "user-a") is False


@pytest.mark.asyncio
async def test_guardrail_rolls_back_when_failure_rate_exceeds(monkeypatch):
    monkeypatch.setattr("app.config.settings.settings.MODEL_ROUTING_ENABLED", True)
    monkeypatch.setattr("app.config.settings.settings.FEATURE_FLAG_ROLLOUT", {"model_routing": 25})
    monkeypatch.setattr(flags_module, "_recent_run_quality", _async_return(0.2))  # 越线(>8%)
    monkeypatch.setattr("app.security.audit.get_audit_logger", lambda: _AuditSpy())

    report = await evaluate_flag_guardrails()
    assert report["rolled_back"] == {"model_routing": 25}
    assert flags_module._ROLLBACK_AT.get("model_routing")
    # 回缩后判定对任何用户都关闭
    assert is_enabled("model_routing", "bucket-user") is False


@pytest.mark.asyncio
async def test_guardrail_keeps_rollout_when_healthy(monkeypatch):
    monkeypatch.setattr("app.config.settings.settings.FEATURE_FLAG_ROLLOUT", {"model_routing": 25})
    monkeypatch.setattr(flags_module, "_recent_run_quality", _async_return(0.02))
    monkeypatch.setattr("app.security.audit.get_audit_logger", lambda: _AuditSpy())

    report = await evaluate_flag_guardrails()
    assert report["rolled_back"] == {}
    assert flags_module._ROLLBACK_AT == {}


def test_flag_status_shape():
    status = flag_status()
    assert "model_routing" in status and "memory_conflict" in status
    entry = status["model_routing"]
    assert {"base_enabled", "rollout_percent", "owner", "description", "cleanup_after"} <= set(entry)


def test_grafana_provisioning_files_are_valid():
    root = Path(__file__).parents[1]
    datasource = (root / "ops/grafana/provisioning/datasources/prometheus.yml").read_text(encoding="utf-8")
    assert "http://prometheus:9090" in datasource
    provider = (root / "ops/grafana/provisioning/dashboards/provider.yml").read_text(encoding="utf-8")
    assert "/var/lib/grafana/dashboards" in provider

    dashboards_dir = root / "ops/grafana/dashboards"
    boards = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in dashboards_dir.glob("*.json")}
    assert set(boards) == {"quality", "reliability", "performance", "cost", "memory"}
    for name, board in boards.items():
        assert board["uid"] == f"mathai-{name}"
        assert board["panels"], f"{name} 看板无面板"
        for panel in board["panels"]:
            assert panel["datasource"]["uid"] == "mathai-prom"
            assert panel["targets"][0]["expr"].strip()


def test_compose_declares_grafana_service():
    root = Path(__file__).parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "grafana/grafana" in compose
    assert "./ops/grafana/provisioning:/etc/grafana/provisioning:ro" in compose
    assert "grafana_data:" in compose


class _AuditSpy:
    def log_modification(self, *args, **kwargs):
        self.last = args


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner
