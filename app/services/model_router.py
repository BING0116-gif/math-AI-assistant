"""模型路由与成本核算(路线图 5.1/5.2/5.3)。

v1 是纯规则路由,零额外模型调用(Step 3.5 教训):
1. 故障状态优先——4.4 failover 粘性切换生效时直接用候选(降级链 L3);
2. MODEL_ROUTING_ENABLED=false(默认)→ 主模型,行为与现状一致;
3. 开启后按 TaskClassifier 档位查 RouteTable,能力校验 fail-closed,
   非常规选择打 mathai_model_route_total{reason="capability"}。

成本核算(5.3)统一读 MODEL_REGISTRY 计价表;未登记价格的模型返回 None,
不拍脑袋估价。
"""

from __future__ import annotations

import logging

from app.config.settings import MODEL_CAPABILITIES, MODEL_REGISTRY

logger = logging.getLogger(__name__)


def _setting(name: str, fallback):
    try:
        from app.config.settings import settings

        return getattr(settings, name)
    except Exception:
        return fallback


class ModelRouter:
    """按任务档位选"够用的最便宜模型";故障粘性与能力校验优先。"""

    def __init__(self, *, enabled: bool | None = None, route_table: dict[str, str] | None = None):
        # enabled=None(生产默认)→ 由 flag 注册表(12.2)按基准设置+灰度分桶判定;
        # 显式 True/False(测试/特殊部署)优先于注册表。
        self._enabled = enabled
        self._route_table = dict(route_table) if route_table is not None else dict(_setting("MATHAI_MODEL_ROUTING", {}) or {})

    @property
    def enabled(self) -> bool:
        return self._enabled is True

    @staticmethod
    def _capability_ok(model: str, required_capabilities: frozenset[str]) -> bool:
        spec = MODEL_CAPABILITIES.get(model)
        if spec is None:
            return False
        return all(bool(spec.get(cap, False)) for cap in required_capabilities)

    def resolve_model(
        self,
        task_type: str,
        *,
        primary_model: str,
        required_capabilities: frozenset[str] = frozenset({"tool_call"}),
        bucket_key: str | None = None,
    ) -> str:
        """返回本次 run 应使用的模型;非常规选择记 mathai_model_route_total。

        bucket_key(通常为 user:session 复合键)驱动 12.2/8.4 的灰度分桶;
        不提供时退化为基准 settings 开关。
        """
        if not primary_model:
            return primary_model

        # 0) 路由开关:显式构造参数优先;生产默认走 flag 注册表(基准设置×灰度分桶)
        if self._enabled is not None:
            routing_on = self._enabled
        else:
            try:
                from app.services.feature_flags import is_enabled as flag_enabled

                routing_on = flag_enabled("model_routing", bucket_key)
            except Exception:
                routing_on = False

        # 1) 故障粘性优先(4.4 骨架收编,5.1:故障状态覆盖路由表)
        try:
            from agent_core.model_failover import get_model_failover_coordinator

            sticky = get_model_failover_coordinator().current_model(primary_model, required_capabilities)
        except Exception:
            sticky = primary_model
        if sticky != primary_model:
            return sticky

        # 2) 规则路由开关
        if not routing_on:
            return primary_model
        target = self._route_table.get(str(task_type))
        if not target or target == primary_model:
            return primary_model
        # 3) 能力校验 fail-closed:未登记或能力不足的候选不参与路由
        if not self._capability_ok(target, required_capabilities):
            logger.warning(f"[ROUTER] 路由候选 {target} 能力不满足 {sorted(required_capabilities)},保持主模型")
            return primary_model
        try:
            from app.observability import MODEL_ROUTE

            MODEL_ROUTE.labels(primary_model[:80], target[:80], "capability").inc()
        except Exception:
            pass
        return target

    @staticmethod
    def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
        """按注册表计价(元/百万 token);未登记价格的模型返回 None。"""
        spec = MODEL_REGISTRY.get(model)
        if spec is None:
            return None
        price_in = spec.get("price_in_per_m")
        price_out = spec.get("price_out_per_m")
        if price_in is None or price_out is None:
            return None
        return round(
            (max(0, prompt_tokens) / 1_000_000) * float(price_in)
            + (max(0, completion_tokens) / 1_000_000) * float(price_out),
            6,
        )


_ROUTER: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = ModelRouter()
    return _ROUTER


def reset_model_router() -> None:
    """测试钩子:重置进程级单例。"""
    global _ROUTER
    _ROUTER = None
