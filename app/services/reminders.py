"""站内提醒中心：把已有学习事实派生成"现在该做什么"的只读聚合。

设计约束（提醒中心不引入第二份真值）：
- 不建 notifications 表、不新增查询语义，输入完全来自 ``learning_hub.due_reviews``
  与 ``learning_hub.today_hub``，因此提醒天然按 user_id 隔离，且与排期真值不会漂移。
- "稍后提醒"复用既有 ``defer_review``（``deferred_until`` + ``idempotency_key``），
  本模块只负责判断"能不能 defer"，不写任何状态。
- 错题级排期项（``source == "error_item"``）没有 ``deferred_until`` 字段，因此
  明确不可 defer，前端据此禁用按钮。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.learning_hub import due_reviews, today_hub

REMINDERS_VERSION = "reminders-derived-v1"

#: 逾期超过该窗口即归入 overdue，否则归入 today（"今日到期"与"陈年欠账"分开呈现）。
OVERDUE_WINDOW_HOURS = 24
#: 未来该窗口内到期的排期归入 upcoming，用于"稍后要看"的预览，不参与角标紧迫度。
UPCOMING_WINDOW_HOURS = 48

BUCKET_OVERDUE = "overdue"
BUCKET_TODAY = "today"
BUCKET_UPCOMING = "upcoming"

KIND_REVIEW = "review_schedule"
KIND_ERROR_REVIEW = "error_review"

#: 错题级项不可延后的原因文案：这是能力边界，不是接口错误。
ERROR_ITEM_DEFER_DISABLED = "错题复习节奏由错题本自动排期，暂不支持单独稍后提醒"


def _utc(value: datetime) -> datetime:
    """SQLite 读回的 DateTime 是 naive，统一按 UTC 归一后再做时间比较。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _parse_due(value: Any) -> datetime | None:
    """排期 payload 里的 due_at 是 ISO 字符串；错题级在缺排期时可能是空串。"""
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _duration(minutes: int) -> str:
    minutes = max(int(minutes), 0)
    days, rest = divmod(minutes, 60 * 24)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if not parts:
        parts.append(f"{max(mins, 1)} 分钟")
    return " ".join(parts)


def _classify(due: datetime | None, now: datetime) -> tuple[str, int, str]:
    """返回 (档位, 逾期分钟, 中文提示)。due 缺失按"今日到期"处理，不静默丢弃提醒。"""
    if due is None:
        return BUCKET_TODAY, 0, "今日到期"
    # 边界按契约取左闭右开：due_at == now-24h 仍属 today，只有严格早于该时刻才算逾期。
    if due < now - timedelta(hours=OVERDUE_WINDOW_HOURS):
        return BUCKET_OVERDUE, int((now - due).total_seconds() // 60), f"逾期 {_duration((now - due).total_seconds() // 60)}"
    if due <= now:
        return BUCKET_TODAY, int((now - due).total_seconds() // 60), "今日到期"
    ahead = int((due - now).total_seconds() // 60)
    if ahead <= UPCOMING_WINDOW_HOURS * 60:
        return BUCKET_UPCOMING, 0, f"{_duration(ahead)}后到期"
    return "", 0, ""


def _point_name(entry: dict[str, Any]) -> str:
    return entry.get("knowledge_point_name") or entry.get("knowledge_point_code") or "该知识点"


def _action(entry: dict[str, Any]) -> dict[str, Any] | None:
    """深链一律复用既有路由与其参数语义：
    错题级 → ``/error-book/:errorId``（ErrorBookView 已按 ``item_id`` 打开详情）；
    知识点级 → ``/knowledge?point=<code>``（KnowledgeCatalogView 的 point 参数已支持 code）。
    """
    if (entry.get("source") or "knowledge_point") == "error_item":
        error_item_id = entry.get("error_item_id")
        return {"route": f"/error-book/{error_item_id}", "query": {}} if error_item_id else None
    code = entry.get("knowledge_point_code")
    return {"route": "/knowledge", "query": {"point": code}} if code else None


def _to_reminder(entry: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    due = _parse_due(entry.get("due_at"))
    bucket, overdue_minutes, hint = _classify(due, now)
    if not bucket:
        return None
    source = entry.get("source") or "knowledge_point"
    raw_id = entry.get("id")
    # 知识点级排期 id 是整型主键（defer/complete 需要）；错题级是 "error-{uuid}" 字符串。
    schedule_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else None
    is_error = source == "error_item"
    name = _point_name(entry)
    return {
        "key": f"{'error_review' if is_error else 'review_schedule'}:{raw_id}",
        "kind": KIND_ERROR_REVIEW if is_error else KIND_REVIEW,
        "bucket": bucket,
        "source": source,
        "schedule_id": schedule_id,
        "error_item_id": entry.get("error_item_id"),
        "question_id": entry.get("question_id"),
        "knowledge_point_code": entry.get("knowledge_point_code") or "",
        "knowledge_point_name": name,
        "due_at": due,
        "overdue_minutes": overdue_minutes,
        "title": f"重练错题 · {name}" if is_error else f"复习 {name}",
        "hint": hint,
        "interval_days": entry.get("interval_days"),
        "review_count": entry.get("review_count"),
        "algorithm_version": entry.get("algorithm_version") or "",
        "action": _action(entry),
        "can_defer": schedule_id is not None,
        "defer_disabled_reason": ERROR_ITEM_DEFER_DISABLED if is_error else None,
    }


async def build_reminders(user_id: str, *, limit: int = 50) -> dict[str, Any]:
    """派生提醒列表 + 角标计数 + 今日主任务。只读，不产生任何持久化状态。

    两次 ``due_reviews`` 取并集（到期项 + 含未来项）而不是只看一次：
    ``include_upcoming=True`` 的窗口按 due_at 升序截断，而被推迟的排期其
    ``effective_due`` 可能晚于 ``due_at``，仅取一次会漏掉"刚被 defer 回来"的项。
    """
    now = datetime.now(timezone.utc)
    due = await due_reviews(user_id, limit=limit)
    wide = await due_reviews(user_id, limit=limit, include_upcoming=True)
    hub = await today_hub(user_id, limit=1)

    merged: dict[str, dict[str, Any]] = {}
    for entry in [*wide.get("items", []), *due.get("items", [])]:
        raw_id = entry.get("id")
        key = f"{'error_review' if (entry.get('source') or '') == 'error_item' else 'review_schedule'}:{raw_id}"
        merged.setdefault(key, entry)

    items = [item for item in (_to_reminder(entry, now) for entry in merged.values()) if item]
    items.sort(key=lambda item: (item["due_at"] is None, item["due_at"] or now))

    counts = {
        BUCKET_OVERDUE: sum(1 for item in items if item["bucket"] == BUCKET_OVERDUE),
        BUCKET_TODAY: sum(1 for item in items if item["bucket"] == BUCKET_TODAY),
        BUCKET_UPCOMING: sum(1 for item in items if item["bucket"] == BUCKET_UPCOMING),
        "total": len(items),
    }
    return {
        "generated_at": now,
        "version": REMINDERS_VERSION,
        "counts": counts,
        "items": items,
        "primary": (hub or {}).get("primary"),
    }
