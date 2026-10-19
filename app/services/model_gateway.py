"""Small provider-neutral model gateway used by model-facing services."""
from __future__ import annotations
import asyncio, time, uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

@dataclass
class GatewayResult:
    value: Any
    provider: str
    model: str | None
    request_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float | None
    fallback_reason: str | None = None
    quality_flags: list[str] | None = None

class ModelGateway:
    def __init__(self, *, timeout_seconds: float = 30, max_retries: int = 1, cost_per_1k_input: float = 0.0, cost_per_1k_output: float = 0.0):
        self.timeout_seconds, self.max_retries = timeout_seconds, max(0, max_retries)
        self.cost_per_1k_input, self.cost_per_1k_output = cost_per_1k_input, cost_per_1k_output

    async def call(self, operation: Callable[[], Awaitable[Any]], *, provider: str, model: str | None = None,
                   fallback: Callable[[Exception], Awaitable[Any]] | None = None) -> GatewayResult:
        request_id, started, error = str(uuid.uuid4()), time.perf_counter(), None
        for attempt in range(self.max_retries + 1):
            try:
                raw = await asyncio.wait_for(operation(), timeout=self.timeout_seconds)
                usage = getattr(raw, "usage", None) or (raw.get("usage", {}) if isinstance(raw, dict) else {})
                inp, out = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0), int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
                return GatewayResult(raw, provider, getattr(raw, "model", None) or model, request_id, int((time.perf_counter()-started)*1000), inp, out, (inp/1000*self.cost_per_1k_input + out/1000*self.cost_per_1k_output))
            except Exception as exc:
                error = exc
                if attempt < self.max_retries: await asyncio.sleep(0.05 * (2 ** attempt))
        if fallback is None: raise error
        value = await fallback(error)
        return GatewayResult(value, "fallback", model, request_id, int((time.perf_counter()-started)*1000), 0, 0, 0.0, type(error).__name__, ["fallback"])
