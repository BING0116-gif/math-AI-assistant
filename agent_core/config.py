"""Configuration objects for :class:`agent_core.agent.MathAgent`.

This module deliberately avoids importing the tool registry at runtime, which
keeps the configuration layer free of a tool-to-agent circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.config.settings import settings

if TYPE_CHECKING:
    from tools import ToolRegistry


@dataclass
class LLMConfig:
    """LLM settings; defaults follow the application configuration."""

    model: str = field(default_factory=lambda: settings.LLM_MODEL or "deepseek-chat")
    temperature: float = 0
    base_url: str = field(
        default_factory=lambda: settings.LLM_API_BASE or "https://api.deepseek.com/v1"
    )


@dataclass
class StrategyConfig:
    """Agent execution strategy settings."""

    max_iterations: int = 5
    stream: bool = True


@dataclass
class DynamicParamsConfig:
    """Dynamic model parameter selection settings."""

    enabled: bool = True


@dataclass
class MathAgentConfig:
    """Complete dependency/configuration object for ``MathAgent``."""

    api_key: str
    llm: LLMConfig = field(default_factory=LLMConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    dynamic_params: DynamicParamsConfig = field(default_factory=DynamicParamsConfig)
    registry: Optional["ToolRegistry"] = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("api_key 不能为空")


__all__ = [
    "DynamicParamsConfig",
    "LLMConfig",
    "MathAgentConfig",
    "StrategyConfig",
]
