from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import admin_agent_metrics_api


def _request(user=None):
    request = Request({"type": "http", "method": "GET", "path": "/api/admin/agent-metrics", "headers": [], "state": {}})
    if user is not None:
        request.state.current_user = user
    return request


class _Sample:
    def __init__(self, name, value, labels=None):
        self.name = name
        self.value = value
        self.labels = labels or {}


class _Family:
    def __init__(self, name, samples):
        self.name = name
        self.samples = samples


class _Registry:
    def collect(self):
        return [
            _Family("mathai_agent_runs", [_Sample("mathai_agent_runs_total", 4, {"capability": "tutor", "status": "completed"})]),
            _Family("mathai_agent_run_duration_seconds", [
                _Sample("mathai_agent_run_duration_seconds_count", 2),
                _Sample("mathai_agent_run_duration_seconds_sum", 3.0),
            ]),
            _Family("mathai_agent_tokens", [_Sample("mathai_agent_tokens_total", 12, {"kind": "input"})]),
        ]


def test_snapshot_is_aggregate_and_process_cumulative():
    snapshot = admin_agent_metrics_api.build_agent_metrics_snapshot(_Registry())
    assert snapshot["semantics"] == "process_cumulative"
    assert snapshot["runs"] == {"completed": 4}
    assert snapshot["tokens"] == {"input": 12}
    assert snapshot["latency"]["observations"] == 2
    assert snapshot["latency"]["average_seconds"] == 1.5
    assert "user_id" not in str(snapshot)
    assert "capability" not in str(snapshot)


@pytest.mark.asyncio
async def test_metrics_requires_admin():
    with pytest.raises(HTTPException) as exc:
        await admin_agent_metrics_api.get_agent_metrics(_request(SimpleNamespace(role="student")))
    assert exc.value.status_code == 403
