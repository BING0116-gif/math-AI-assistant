"""Low-cardinality metrics and privacy-safe structured logging."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

request_id_var = contextvars.ContextVar("request_id", default="-")
user_id_var = contextvars.ContextVar("user_id", default="-")

HTTP_REQUESTS = Counter("mathai_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("mathai_http_request_duration_seconds", "HTTP request latency", ["method", "route"])
GRADING_RESULTS = Counter("mathai_grading_results_total", "Grading outcomes", ["outcome"])
AI_CALLS = Counter("mathai_ai_calls_total", "AI calls", ["provider", "model", "status"])
AI_LATENCY = Histogram("mathai_ai_call_duration_seconds", "AI call latency", ["provider", "model"])
AI_TOKENS = Counter("mathai_ai_tokens_total", "AI tokens", ["provider", "model", "kind"])
AI_COST = Counter("mathai_ai_estimated_cost_total", "Estimated AI cost", ["provider", "model", "currency"])
AGENT_RUNS = Counter("mathai_agent_runs_total", "Agent runs", ["capability", "status"])
AGENT_LATENCY = Histogram(
    "mathai_agent_run_duration_seconds", "End-to-end Agent run latency",
    ["capability"], buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60],
)
AGENT_TTFT = Histogram(
    "mathai_agent_time_to_first_token_seconds", "Agent time to first content token",
    ["capability"], buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
)
AGENT_TOKENS = Counter("mathai_agent_tokens_total", "Tokens consumed by Agent runs", ["kind"])
AGENT_TOOL_CALLS = Counter("mathai_agent_tool_calls_total", "Agent tool calls", ["tool", "status"])
AGENT_TOOL_LATENCY = Histogram(
    "mathai_agent_tool_duration_seconds", "Agent tool duration", ["tool"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)
AGENT_CONTEXT = Histogram(
    "mathai_agent_context_chars", "Bounded Agent history characters",
    buckets=[500, 1000, 2000, 4000, 8000, 12000, 20000],
)
AGENT_CONTEXT_TRIMS = Counter("mathai_agent_context_trims_total", "Context trims", ["reason"])
SSE_EVENTS = Counter("mathai_sse_events_total", "SSE events emitted", ["event_type"])
CONTENT_EVENTS = Counter("mathai_content_events_total", "Content operations", ["operation", "status"])
RECOVERY_RUNS = Counter("mathai_recovery_runs_total", "Recovery/repair runs", ["operation", "status"])

# 阶段一质量闭环指标（1-A）。这些指标只描述低基数的质量/路由状态，
# 不携带 user_id、问题内容或模型输出，避免把学生数据写入 Prometheus。
AGENT_CRITIC_VERDICTS = Counter(
    "mathai_agent_critic_verdicts_total",
    "Answer Critic verdicts",
    ["verdict", "capability"],
)
AGENT_ANSWER_MODIFIED = Counter(
    "mathai_agent_answer_modified_total",
    "Answers modified by users",
    ["source"],
)
AGENT_FOLLOWUP = Counter(
    "mathai_agent_followup_total",
    "Follow-up questions associated with an Agent run",
    ["gap"],
)
AGENT_REVIEW_SAMPLED = Counter(
    "mathai_agent_review_sampled_total",
    "Agent runs sampled for quality review",
    ["queue"],
)
AGENT_REVIEW_VERDICTS = Counter(
    "mathai_agent_review_verdicts_total",
    "Quality review verdicts",
    ["verdict", "reviewer_type"],
)
MODEL_ROUTE = Counter(
    "mathai_model_route_total",
    "Model route transitions",
    ["from", "to", "reason"],
)
TOOL_CIRCUIT_STATE = Gauge(
    "mathai_tool_circuit_state",
    "Current circuit breaker state (0/1) by tool and state",
    ["tool", "state"],
)
TOOL_RETRIES = Counter(
    "mathai_tool_retry_total",
    "Bounded tool retry attempts",
    ["tool", "outcome"],
)

_SENSITIVE = re.compile(r"(authorization|password|secret|api[_-]?key|token|prompt|answer|content)", re.I)


def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if _SENSITIVE.search(str(k)) else sanitize(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, depth + 1) for v in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
        }
        for key in ("session_id", "model_run_id", "tool", "question_id", "event_id", "operation"):
            if hasattr(record, key): payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)[:2000]
        return json.dumps(sanitize(payload), ensure_ascii=False, default=str)


def configure_json_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp): self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        requested = headers.get(b"x-request-id", b"").decode("ascii", "ignore")[:128]
        rid = requested if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", requested or "") else str(uuid.uuid4())
        token = request_id_var.set(rid)
        started, status = time.perf_counter(), 500
        async def send_with_context(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode("ascii")))
            await send(message)
        try:
            await self.app(scope, receive, send_with_context)
        finally:
            route_obj = scope.get("route")
            route = getattr(route_obj, "path", None) or ("/unmatched" if status == 404 else "/unknown")
            method = scope.get("method", "UNKNOWN")
            HTTP_REQUESTS.labels(method, route, str(status)).inc()
            HTTP_LATENCY.labels(method, route).observe(time.perf_counter() - started)
            request_id_var.reset(token)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
