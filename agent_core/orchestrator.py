"""T10：在既有 MathAgent 之外增加教学任务编排层。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from agent_core.capabilities import Capability, DiagnoseErrorCapability, SolveCapability
from agent_core.capabilities.base import CapabilityManifest
from app.services.mode_gating import normalize_tutor_mode


LegacyStrategySelector = Callable[[str, str], Awaitable[Any]]


@dataclass(frozen=True)
class CapabilityRoute:
    """一次编排的只读结果；SSE 仍消费旧策略产出的文本事件。"""

    manifest: CapabilityManifest
    strategy: Any


class MathOrchestrator:
    """集中选择 Capability，并把工具边界交给旧策略装配。

    它不创建新的 Agent、不改写 SSE，也不持有学生数据。user_id/session_id
    继续由 MathAgent 的既有上下文与会话键隔离。
    """

    def __init__(
        self,
        strategy_selector: LegacyStrategySelector,
        capabilities: Sequence[Capability] | None = None,
    ):
        self._strategy_selector = strategy_selector
        self._capabilities = tuple(capabilities or (DiagnoseErrorCapability(), SolveCapability()))
        if not self._capabilities:
            raise ValueError("at least one capability is required")

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return self._capabilities

    def select_capability(self, user_input: str, context: Mapping[str, Any]) -> Capability:
        canonical_mode = normalize_tutor_mode(context.get("tutor_mode", "tutor_free"))
        for capability in self._capabilities:
            if canonical_mode in capability.manifest.supported_modes and capability.matches(user_input, context):
                return capability
        # Solve 是安全默认值；若未来新增 Capability 配置错误，仍保持旧入口可用。
        return next(cap for cap in self._capabilities if cap.manifest.name == "solve")

    async def route(
        self, user_input: str, session_id: str, context: dict[str, Any]
    ) -> CapabilityRoute:
        capability = self.select_capability(user_input, context)
        capability.apply_context(context)
        # 严格复用 MathAgent 的既有策略选择（动态参数、ReAct/未来 Planned）。
        strategy = await self._strategy_selector(user_input, session_id)
        return CapabilityRoute(manifest=capability.manifest, strategy=strategy)
