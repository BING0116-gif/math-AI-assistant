"""管理员 Agent 运行指标接口。

只暴露当前进程内 Prometheus 累计指标的低基数聚合，不返回用户、会话、
工具参数、题目正文或模型输出。长期趋势和窗口化 P95 应由 Prometheus/Grafana
根据 /metrics 端点计算；本接口用于管理员页面快速查看当前进程状态。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from prometheus_client import REGISTRY

from app.security.access_control import require_admin_role

router = APIRouter(prefix="/api/admin", tags=["管理员 Agent 指标"])


def _families(registry: Any) -> dict[str, Any]:
    return {family.name: family for family in registry.collect()}


def _counter_by_label(families: dict[str, Any], name: str, label: str) -> dict[str, int]:
    family = families.get(name)
    if family is None:
        return {}
    result: dict[str, int] = {}
    for sample in family.samples:
        value = sample.labels.get(label)
        if value:
            result[value] = result.get(value, 0) + int(sample.value)
    return result


def _histogram_summary(families: dict[str, Any], name: str) -> dict[str, float | int]:
    family = families.get(name)
    if family is None:
        return {"observations": 0, "total_seconds": 0.0, "average_seconds": 0.0}
    # collect() exposes _count and _sum as separate sample names.
    count = sum(int(sample.value) for sample in family.samples if sample.name == f"{name}_count")
    total = sum(float(sample.value) for sample in family.samples if sample.name == f"{name}_sum")
    return {
        "observations": count,
        "total_seconds": round(total, 6),
        "average_seconds": round(total / count, 6) if count else 0.0,
    }


def _histogram_value_summary(families: dict[str, Any], name: str, value_key: str) -> dict[str, float | int]:
    family = families.get(name)
    if family is None:
        return {"observations": 0, f"total_{value_key}": 0.0, f"average_{value_key}": 0.0}
    count = sum(int(sample.value) for sample in family.samples if sample.name == f"{name}_count")
    total = sum(float(sample.value) for sample in family.samples if sample.name == f"{name}_sum")
    return {
        "observations": count,
        f"total_{value_key}": round(total, 3),
        f"average_{value_key}": round(total / count, 3) if count else 0.0,
    }


def build_agent_metrics_snapshot(registry: Any = REGISTRY) -> dict[str, Any]:
    """Build a privacy-safe cumulative snapshot from a Prometheus registry."""
    families = _families(registry)
    return {
        "semantics": "process_cumulative",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "runs": _counter_by_label(families, "mathai_agent_runs", "status"),
        "tool_calls": _counter_by_label(families, "mathai_agent_tool_calls", "status"),
        "tokens": _counter_by_label(families, "mathai_agent_tokens", "kind"),
        "sse_events": _counter_by_label(families, "mathai_sse_events", "event_type"),
        "context_trims": _counter_by_label(families, "mathai_agent_context_trims", "reason"),
        "context": _histogram_value_summary(families, "mathai_agent_context_chars", "chars"),
        "latency": _histogram_summary(families, "mathai_agent_run_duration_seconds"),
        "time_to_first_token": _histogram_summary(families, "mathai_agent_time_to_first_token_seconds"),
        "tool_latency": _histogram_summary(families, "mathai_agent_tool_duration_seconds"),
    }


@router.get("/agent-metrics")
async def get_agent_metrics(request: Request):
    require_admin_role(request)
    return {"code": 0, "data": build_agent_metrics_snapshot()}
