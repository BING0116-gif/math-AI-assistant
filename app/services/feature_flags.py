"""Feature Flag 注册表与灰度分桶(路线图 12.2/8.4,阶段六)。

- settings(env)为基准值;灰度放量比例来自 FEATURE_FLAG_ROLLOUT(JSON,
  {flag: percent});同 user key 稳定分桶(SHA-256),同 key 恒同桶;
- 护栏自动回缩(8.4):灰度生效期间,若近期 run 失败+超时率越线,
  evaluate_flag_guardrails() 将该 flag 放量自动置 0 并留审计日志;
- 每个 flag 登记 owner 与用途;发布后两周内转正或回退,不留僵尸 flag。

v1 简化(与 8.4 的偏差,已在路线图注记):护栏比对按时间窗口的总量失败率,
不做"灰度桶 vs 对照桶"分组对比——指标保持低基数、不写 user_id 标签。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.config.settings import settings

logger = logging.getLogger(__name__)

# flag 注册表:名称 → 基准 settings 字段与元数据(12.2)
FLAG_REGISTRY: Dict[str, Dict[str, Any]] = {
    "model_routing": {
        "settings_field": "MODEL_ROUTING_ENABLED",
        "owner": "backend",
        "description": "阶段三规则路由:按任务档位选模型",
        "cleanup_after": "2026-11-04",
    },
    "memory_conflict": {
        "settings_field": "MEMORY_CONFLICT_ENABLED",
        "owner": "backend",
        "description": "阶段四记忆冲突仲裁",
        "cleanup_after": "2026-11-04",
    },
}


def _rollout_table() -> Dict[str, int]:
    table = getattr(settings, "FEATURE_FLAG_ROLLOUT", None)
    if isinstance(table, dict):
        return {str(k): max(0, min(100, int(v))) for k, v in table.items()}
    return {}


def bucket_percent(flag: str, user_key: str) -> int:
    """稳定分桶:同 flag+key 恒返回同一 0–99 值。"""
    digest = hashlib.sha256(f"{flag}:{user_key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


def is_enabled(flag: str, user_key: str | None = None) -> bool:
    """flag 判定:基准 settings 开关 AND(user_key 分桶 ≤ 放量比例)。

    未注册 flag 或无 user_key 时退化为基准 settings 值(现状行为);
    护栏回缩过的 flag 对所有用户即时关闭。
    """
    if flag in _ROLLBACK_AT:
        return False
    entry = FLAG_REGISTRY.get(flag)
    base = bool(getattr(settings, entry["settings_field"])) if entry else False
    if not entry or not user_key:
        return base
    percent = _rollout_table().get(flag)
    if percent is None:
        return base
    if percent >= 100:
        return base
    if percent <= 0:
        return False
    return base and bucket_percent(flag, user_key) < percent


async def _recent_run_quality(window: int = 50) -> float:
    """近 window 条已结束 run 中失败+超时占比(护栏信号,与用户无关)。"""
    try:
        from sqlalchemy import select

        from app.data.database import get_db_session
        from app.data.models import AIInteractionRun

        async with get_db_session() as db:
            rows = list((await db.execute(
                select(AIInteractionRun.status)
                .where(AIInteractionRun.status != "started")
                .order_by(AIInteractionRun.created_at.desc())
                .limit(window)
            )).scalars())
        if not rows:
            return 0.0
        bad = sum(1 for status in rows if status in {"failed", "timeout", "failed_l4"})
        return bad / len(rows)
    except Exception as exc:
        logger.warning(f"[FLAGS] 护栏信号查询失败(按健康处理): {exc}")
        return 0.0


# 护栏自动回缩内存态:flag → 置 0 时间;进程内即时生效(短 TTL 语义的 v1)
_ROLLBACK_AT: Dict[str, str] = {}


async def evaluate_flag_guardrails(*, failure_rate_threshold: float = 0.08) -> Dict[str, Any]:
    """8.4 护栏自动回缩:越线 → 该 flag 放量置 0 + 审计日志。

    由调度器周期调用;返回报告供运维与看板消费。
    """
    rolled_back: Dict[str, int] = {}
    quality = await _recent_run_quality()
    if quality > failure_rate_threshold:
        table = _rollout_table()
        for flag, percent in table.items():
            if percent > 0 and flag in FLAG_REGISTRY:
                _ROLLBACK_AT[flag] = datetime.now(timezone.utc).isoformat()
                rolled_back[flag] = percent
                logger.warning(
                    f"[FLAGS] 护栏越线(近 50 run 失败率 {quality:.1%}),灰度自动回缩: "
                    f"flag={flag} rollout {percent}% -> 0%"
                )
                try:
                    from app.security.audit import get_audit_logger

                    get_audit_logger().log_modification(
                        "system", "feature_flag", flag,
                        old_value={"rollout_percent": percent},
                        new_value={"rollout_percent": 0},
                        changed_fields=["rollout_percent"],
                    )
                except Exception:
                    pass
    return {"recent_bad_rate": round(quality, 4), "threshold": failure_rate_threshold, "rolled_back": rolled_back}


def flag_status() -> Dict[str, Any]:
    """注册表快照:基准值、当前放量、回缩记录(管理端可消费)。"""
    table = _rollout_table()
    return {
        flag: {
            "base_enabled": bool(getattr(settings, entry["settings_field"])),
            "rollout_percent": table.get(flag, 100 if bool(getattr(settings, entry["settings_field"])) else 0)
            if flag not in _ROLLBACK_AT else 0,
            "rolled_back_at": _ROLLBACK_AT.get(flag),
            "owner": entry["owner"],
            "description": entry["description"],
            "cleanup_after": entry["cleanup_after"],
        }
        for flag, entry in FLAG_REGISTRY.items()
    }
