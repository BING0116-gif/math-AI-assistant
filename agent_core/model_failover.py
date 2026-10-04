"""故障驱动的备用模型切换（路线图 4.4.2，L3）。

阶段二只交付 failover 骨架：
- 窗口内连续失败达到阈值 → 粘性切换到下一个满足能力要求的候选模型；
- 切换打 mathai_model_route_total{reason="degrade"}；
- 候选与主模型共用 endpoint/密钥（跨供应商的 base_url/api_key 映射
  留待阶段三模型注册表统一收编）；
- 能力校验 fail-closed：未在 MODEL_CAPABILITIES 登记或能力不满足的候选直接跳过；
- 探测回切：候选上运行超过 LLM_FAILOVER_PROBE_SECONDS 后自动回主模型，
  主模型仍失败会再次触发切换。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable, Iterable

from app.config.settings import MODEL_CAPABILITIES

logger = logging.getLogger(__name__)


def _budget_setting(name: str, fallback):
    try:
        from app.config.settings import settings

        return getattr(settings, name)
    except Exception:
        return fallback


class ModelFailoverCoordinator:
    """粘性故障转移协调器（进程级单例）。

    失败窗口跨 run 累计；成功只清空失败窗口，不改变粘性状态；
    回切纯粹由探测计时器驱动，避免主模型抖动导致频繁来回切换。
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        candidates: Iterable[str] | None = None,
        window_seconds: float | None = None,
        failure_threshold: int | None = None,
        probe_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._enabled = enabled if enabled is not None else _budget_setting("LLM_FAILOVER_ENABLED", False)
        self._candidates = list(candidates) if candidates is not None else list(_budget_setting("LLM_FALLBACK_MODELS", []) or [])
        self._window_seconds = window_seconds if window_seconds is not None else _budget_setting("LLM_FAILOVER_WINDOW_SECONDS", 60.0)
        self._failure_threshold = failure_threshold if failure_threshold is not None else _budget_setting("LLM_FAILOVER_FAILURES", 3)
        self._probe_seconds = probe_seconds if probe_seconds is not None else _budget_setting("LLM_FAILOVER_PROBE_SECONDS", 300.0)
        self._clock = clock
        self._failures: deque[float] = deque()
        # -1 = 主模型；否则为 self._candidates 的下标
        self._active_index = -1
        self._switched_at: float | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._enabled and self._candidates)

    def _capability_ok(self, model: str, required_capabilities: frozenset[str]) -> bool:
        spec = MODEL_CAPABILITIES.get(model)
        if spec is None:
            # 未登记能力表的模型不能参与切换（fail-closed，宁可不切）。
            return False
        return all(bool(spec.get(cap, False)) for cap in required_capabilities)

    def eligible_candidates(self, required_capabilities: frozenset[str]) -> list[str]:
        return [m for m in self._candidates if self._capability_ok(m, required_capabilities)]

    def current_model(self, primary_model: str, required_capabilities: frozenset[str] = frozenset({"tool_call"})) -> str:
        """当前应使用的模型：主模型，或粘性候选（探测期到则回主模型）。"""
        if not self.enabled or self._active_index < 0:
            return primary_model
        candidates = self.eligible_candidates(required_capabilities)
        if self._active_index >= len(candidates):
            self._reset()
            return primary_model
        if self._switched_at is not None and self._clock() - self._switched_at >= self._probe_seconds:
            logger.info("[FAILOVER] 探测期结束，回切主模型")
            self._reset()
            return primary_model
        return candidates[self._active_index]

    def record_failure(self, primary_model: str, required_capabilities: frozenset[str] = frozenset({"tool_call"})) -> str | None:
        """记录一次 LLM 失败；达到阈值则粘性切换，返回切换到的模型（无候选返回 None → L4）。"""
        if not self.enabled:
            return None
        now = self._clock()
        self._failures.append(now)
        while self._failures and now - self._failures[0] > self._window_seconds:
            self._failures.popleft()
        if len(self._failures) < self._failure_threshold:
            return None
        if self._switched_at is not None and now - self._switched_at < self._probe_seconds:
            # 粘性期内不重复切换；候选上的失败同样累计，探测期到后再决定。
            return None
        candidates = self.eligible_candidates(required_capabilities)
        next_index = self._active_index + 1
        if next_index >= len(candidates):
            logger.warning("[FAILOVER] 候选模型已耗尽，保持当前模型（由调用方走 L4 模板）")
            self._failures.clear()
            return None
        from_model = self.current_model(primary_model, required_capabilities)
        self._active_index = next_index
        self._switched_at = now
        self._failures.clear()
        to_model = candidates[next_index]
        logger.warning(f"[FAILOVER] 连续失败达阈值，粘性切换模型: {from_model} -> {to_model}")
        try:
            from app.observability import MODEL_ROUTE

            MODEL_ROUTE.labels(from_model[:80], to_model[:80], "degrade").inc()
        except Exception:
            pass
        return to_model

    def record_success(self) -> None:
        """一次成功完成只清空失败窗口；粘性切换由探测计时器回切。"""
        self._failures.clear()

    def _reset(self) -> None:
        self._active_index = -1
        self._switched_at = None
        self._failures.clear()


_COORDINATOR: ModelFailoverCoordinator | None = None


def get_model_failover_coordinator() -> ModelFailoverCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = ModelFailoverCoordinator()
    return _COORDINATOR


def reset_model_failover_coordinator() -> None:
    """测试钩子：重置进程级单例。"""
    global _COORDINATOR
    _COORDINATOR = None
