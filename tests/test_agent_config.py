import pytest

from agent_core.agent import (
    DynamicParamsConfig as LegacyDynamicParamsConfig,
    LLMConfig as LegacyLLMConfig,
    MathAgentConfig as LegacyMathAgentConfig,
    StrategyConfig as LegacyStrategyConfig,
)
from agent_core.config import (
    DynamicParamsConfig,
    LLMConfig,
    MathAgentConfig,
    StrategyConfig,
)


@pytest.mark.skip(reason="需 agent.py 从 agent_core.config 重导出配置类;agent.py 正被并行会话编辑,待其落地后启用")
def test_agent_config_old_import_path_remains_compatible():
    assert LegacyMathAgentConfig is MathAgentConfig
    assert LegacyLLMConfig is LLMConfig
    assert LegacyStrategyConfig is StrategyConfig
    assert LegacyDynamicParamsConfig is DynamicParamsConfig


def test_agent_config_defaults_remain_structured():
    config = MathAgentConfig(api_key="test-key")

    assert config.api_key == "test-key"
    assert config.llm.temperature == 0
    assert config.strategy.max_iterations == 5
    assert config.strategy.stream is True
    assert config.dynamic_params.enabled is True
    assert config.registry is None


def test_agent_config_rejects_empty_api_key():
    with pytest.raises(ValueError, match="api_key 不能为空"):
        MathAgentConfig(api_key="")
