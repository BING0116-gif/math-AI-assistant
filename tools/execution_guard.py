"""Bounded, privacy-safe execution guard for async tools.

The guard owns only execution policy and circuit state.  Tool ownership,
validation, and student-scoped context remain in the existing registry/tool
layers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable

from tools.base_tool import ToolOutput

logger = logging.getLogger(__name__)


def _metric(name: str, tool_name: str, value: str) -> None:
    """Best-effort low-cardinality metrics; never break a tool call."""
    try:
        from app import observability

        metric = getattr(observability, name)
        if name == "TOOL_CIRCUIT_STATE":
            for state in ("closed", "open", "half_open"):
                metric.labels(tool_name[:80], state).set(1 if state == value else 0)
        else:
            metric.labels(tool_name[:80], value).inc()
    except Exception:
        pass


@dataclass(frozen=True)
class GuardPolicy:
    timeout_s: float = 30.0
    retries: int = 0
    retry_backoff_s: float = 0.5
    circuit_enabled: bool = True
    failure_threshold: int = 5
    window_s: float = 30.0
    cooldown_s: float = 60.0


@dataclass
class _Circuit:
    failures: deque[float]
    opened_at: float | None = None
    half_open: bool = False


class ToolExecutionGuard:
    """Run a tool with timeout, bounded retry, and per-tool circuit state."""

    def __init__(self, policy: GuardPolicy | None = None):
        self.policy = policy or GuardPolicy()
        self._circuits: dict[str, _Circuit] = {}

    def _circuit(self, tool_name: str) -> _Circuit:
        return self._circuits.setdefault(tool_name, _Circuit(deque()))

    def _state(self, tool_name: str, now: float) -> str:
        circuit = self._circuit(tool_name)
        if circuit.opened_at is None:
            return "closed"
        if now - circuit.opened_at >= self.policy.cooldown_s:
            circuit.half_open = True
            return "half_open"
        return "open"

    def _record_failure(self, tool_name: str, now: float) -> None:
        circuit = self._circuit(tool_name)
        while circuit.failures and now - circuit.failures[0] > self.policy.window_s:
            circuit.failures.popleft()
        circuit.failures.append(now)
        if len(circuit.failures) >= self.policy.failure_threshold:
            circuit.opened_at = now
            circuit.half_open = False
            _metric("TOOL_CIRCUIT_STATE", tool_name, "open")

    def _record_success(self, tool_name: str) -> None:
        circuit = self._circuit(tool_name)
        circuit.failures.clear()
        circuit.opened_at = None
        circuit.half_open = False
        _metric("TOOL_CIRCUIT_STATE", tool_name, "closed")

    async def run(
        self,
        tool_name: str,
        operation: Callable[[], Awaitable[ToolOutput]],
        *,
        policy: GuardPolicy | None = None,
        retryable: bool = False,
    ) -> ToolOutput:
        policy = policy or self.policy
        now = time.monotonic()
        state = self._state(tool_name, now) if policy.circuit_enabled else "closed"
        if state == "open":
            _metric("TOOL_CIRCUIT_STATE", tool_name, "open")
            return ToolOutput(
                success=False,
                error=f"[TOOL_UNAVAILABLE] {tool_name} 暂不可用(熔断中)，请稍后再试。",
                tool_name=tool_name,
                metadata={"error_code": "TOOL_UNAVAILABLE", "circuit_state": "open"},
            )

        attempts = 1 + (max(0, policy.retries) if retryable else 0)
        last_code = "TOOL_ERROR"
        last_message = "工具执行失败"
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(operation(), timeout=policy.timeout_s)
                if result.success:
                    self._record_success(tool_name)
                    return result
                last_code = "TOOL_ERROR"
                last_message = result.error or "工具返回失败"
            except asyncio.TimeoutError:
                last_code = "TOOL_TIMEOUT"
                last_message = f"{tool_name} 执行超过 {policy.timeout_s:g}s"
            except Exception as exc:  # noqa: BLE001 - normalize tool boundary
                last_code = "TOOL_ERROR"
                last_message = f"{type(exc).__name__}: {str(exc)[:200]}"

            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "工具执行失败 tool=%s code=%s attempt=%s elapsed_ms=%.1f",
                tool_name, last_code, attempt + 1, elapsed_ms,
            )
            if policy.circuit_enabled and not (state == "half_open" and attempt == 0):
                self._record_failure(tool_name, time.monotonic())
            if attempt < attempts - 1:
                _metric("TOOL_RETRIES", tool_name, "scheduled")
                await asyncio.sleep(policy.retry_backoff_s * (2 ** attempt))

        _metric("TOOL_RETRIES", tool_name, "exhausted" if attempts > 1 else "none")
        return ToolOutput(
            success=False,
            error=f"[{last_code}] {last_message}",
            tool_name=tool_name,
            metadata={"error_code": last_code, "attempts": attempts, "circuit_state": self._state(tool_name, time.monotonic()) if policy.circuit_enabled else "disabled"},
        )


def default_guard_policy() -> GuardPolicy:
    """Read reliability settings lazily to avoid config import cycles."""
    try:
        from app.config.settings import settings

        return GuardPolicy(
            timeout_s=settings.AGENT_TOOL_DEFAULT_TIMEOUT_SECONDS,
            retries=settings.AGENT_TOOL_RETRY_MAX,
            retry_backoff_s=settings.TOOL_RETRY_BACKOFF_BASE_SECONDS,
            circuit_enabled=settings.CIRCUIT_ENABLED,
            failure_threshold=settings.CIRCUIT_FAILURE_THRESHOLD,
            window_s=settings.CIRCUIT_WINDOW_SECONDS,
            cooldown_s=settings.CIRCUIT_COOLDOWN_SECONDS,
        )
    except Exception:
        return GuardPolicy()
