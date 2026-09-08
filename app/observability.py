"""Low-cardinality metrics and privacy-safe structured logging."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
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
CONTENT_EVENTS = Counter("mathai_content_events_total", "Content operations", ["operation", "status"])
RECOVERY_RUNS = Counter("mathai_recovery_runs_total", "Recovery/repair runs", ["operation", "status"])

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
