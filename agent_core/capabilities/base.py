"""Capability 的最小抽象，避免第一版过早引入新的 Agent 框架。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CapabilityManifest:
    """一个教学任务可声明的稳定边界。"""

    name: str
    supported_modes: tuple[str, ...]
    stages: tuple[str, ...]
    allowed_tools: frozenset[str]
    strategy_policy: str


class Capability(ABC):
    """选择任务，不拥有或复制 MathAgent/Strategy 的执行实现。"""

    manifest: CapabilityManifest

    @abstractmethod
    def matches(self, user_input: str, context: Mapping[str, Any]) -> bool:
        """当前会话是否应由该 Capability 负责。"""

    def apply_context(self, context: dict[str, Any]) -> None:
        """把 Capability 边界附加到现有请求上下文，供旧策略装配工具。"""
        context["capability"] = self.manifest.name
        context["capability_allowed_tools"] = frozenset(self.manifest.allowed_tools)
        context["capability_strategy_policy"] = self.manifest.strategy_policy
