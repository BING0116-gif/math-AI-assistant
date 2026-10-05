"""阶段三 5.1/5.2/5.3 模型路由与成本核算回归测试。"""

import pytest

from agent_core.model_failover import reset_model_failover_coordinator
from app.services import model_router as router_module
from app.services.model_router import ModelRouter, reset_model_router


@pytest.fixture(autouse=True)
def reset_singletons():
    reset_model_router()
    reset_model_failover_coordinator()
    yield
    reset_model_router()
    reset_model_failover_coordinator()


def test_disabled_router_keeps_primary():
    router = ModelRouter(enabled=False)
    assert router.resolve_model("knowledge", primary_model="deepseek-chat") == "deepseek-chat"
    assert router.enabled is False


def test_enabled_router_sends_simple_tiers_to_light_model(monkeypatch):
    router = ModelRouter(enabled=True)
    assert router.resolve_model("knowledge", primary_model="deepseek-chat") == "deepseek-v4-flash"
    assert router.resolve_model("quick", primary_model="deepseek-chat") == "deepseek-v4-flash"
    # 主力档映射回主模型,不产生切换
    assert router.resolve_model("solution", primary_model="deepseek-chat") == "deepseek-chat"


def test_capability_fail_closed_keeps_primary(monkeypatch):
    monkeypatch.setitem(router_module.MODEL_CAPABILITIES, "deepseek-v4-flash", {"tool_call": False, "json_output": True})
    router = ModelRouter(enabled=True)
    # 轻量档缺 tool_call 能力 → 不路由,保持主模型
    assert router.resolve_model("knowledge", primary_model="deepseek-chat") == "deepseek-chat"


def test_failover_sticky_overrides_route_table(monkeypatch):
    from agent_core.model_failover import ModelFailoverCoordinator
    from agent_core import model_failover as failover_module

    sticky = ModelFailoverCoordinator(
        enabled=True,
        candidates=["deepseek-v4-flash"],
        window_seconds=60.0,
        failure_threshold=1,
        probe_seconds=300.0,
        clock=lambda: 0.0,
    )
    monkeypatch.setattr(failover_module, "_COORDINATOR", sticky)
    sticky.record_failure("deepseek-chat")  # 阈值 1 → 立即粘性切换

    router = ModelRouter(enabled=False)  # 路由开关关闭也不影响故障粘性
    assert router.resolve_model("knowledge", primary_model="deepseek-chat") == "deepseek-v4-flash"


def test_estimate_cost_uses_registry_pricing():
    cost = ModelRouter.estimate_cost("deepseek-chat", 1_000_000, 500_000)
    assert cost == pytest.approx(2.0 + 4.0)
    assert ModelRouter.estimate_cost("unknown-model", 1000, 1000) is None


def test_estimate_cost_handles_negative_and_missing_prices():
    assert ModelRouter.estimate_cost("deepseek-chat", -5, 0) == 0.0
    from app.config.settings import MODEL_REGISTRY

    monkey_spec = dict(MODEL_REGISTRY["deepseek-chat"])
    monkey_spec.pop("price_in_per_m")
    monkeypatch_spec = pytest.MonkeyPatch()
    monkeypatch_spec.setitem(MODEL_REGISTRY, "deepseek-chat", monkey_spec)
    try:
        assert ModelRouter.estimate_cost("deepseek-chat", 1000, 1000) is None
    finally:
        monkeypatch_spec.undo()


def test_factory_get_llm_for_model_is_cached(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from prompts.dynamic_params import DynamicLLMFactory, TaskType

    factory = DynamicLLMFactory(api_key="sk-test", base_url="https://example.invalid/v1", model="deepseek-chat")
    first = factory.get_llm_for_model(TaskType.KNOWLEDGE_QUERY, "deepseek-v4-flash")
    second = factory.get_llm_for_model(TaskType.KNOWLEDGE_QUERY, "deepseek-v4-flash")
    assert first is second
    assert first.model_name == "deepseek-v4-flash"
    # 默认档位仍是主模型
    assert factory.get_llm(TaskType.KNOWLEDGE_QUERY).model_name == "deepseek-chat"
