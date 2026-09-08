"""错题级间隔复习排期（T02 ReviewScheduler）。

职责边界：
- 只负责计算与持久化"错题下次何时复习"（next_review_at / interval / streak）；
- 不直接调用 LLM；不做掌握度计算——复习结果的 mastery 回流走 T01 定义的
  证据口径（practice_answer 等事件 + learning_projection），本模块不重复实现。

审计结论（为什么不用现有 ReviewSchedule）：
- ``review_schedules`` 是知识点级排期，且有 UNIQUE(user_id, knowledge_point_code)
  约束——同一知识点下多道错题会互相覆盖；``complete_review`` 校验的是
  "作答包含该知识点"，无法绑定"重做哪道错题"，故不能表达
  错题级 next_review_at / interval / streak，需要独立字段（Alembic 迁移）。

幂等：复用 ErrorReviewEvent.event_id 唯一约束模式。schedule_after_review 只被
record_review_evidence 在"事件不是重放"分支之后调用，因此同一 attempt 重放
既不会重复推进 review_state，也不会重复延后排期。

第一版策略（简单可解释，阈值见 settings.py，待真实复习数据校准）：
- 新错题首次排期：1 天后；
- 复习答对：间隔 ×2（上限 30 天），streak +1；
- 复习答错 / 再次答错（capture_wrong_attempt 重置）：间隔回到 1 天，streak 清零；
  review_state 被置回 "new"，在 get_due_reviews 中天然置顶（活跃错题优先）；
- 毕业（mastered）：取消排期，不再进入复习队列。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.data.models import ErrorItem

SCHEDULER_VERSION = "error-review-scheduler-v1"

# review_state -> 展示/排序用阶段值（越小越靠前；"活跃错题优先于普通巩固题"）
_STATE_STAGE = {"new": 0, "understanding": 1, "consolidating": 2, "mastered": 3}


def compute_next_interval(*, current_interval_days: int, correct: bool) -> int:
    """根据当前间隔与本次复习结果计算下一次间隔（天）。纯函数，便于测试。"""
    if not correct:
        return settings.REVIEW_FIRST_INTERVAL_DAYS
    base = current_interval_days if current_interval_days > 0 else settings.REVIEW_FIRST_INTERVAL_DAYS
    return min(base * settings.REVIEW_CORRECT_MULTIPLIER, settings.REVIEW_MAX_INTERVAL_DAYS)


def schedule_new_error(item: ErrorItem, *, now: datetime | None = None) -> None:
    """新错题首次排期；再次答错的错题同样走这里（重置为最短间隔并置顶）。

    直接在调用方事务内修改传入的 ORM 对象，不自行 commit/flush——
    由 capture_wrong_attempt 所在事务保证原子性。
    """
    now = now or datetime.now(timezone.utc)
    interval = settings.REVIEW_FIRST_INTERVAL_DAYS
    item.review_interval_days = interval
    item.review_streak = 0
    item.next_review_at = now + timedelta(days=interval)
    item.scheduler_version = SCHEDULER_VERSION


def schedule_after_review(item: ErrorItem, *, correct: bool, now: datetime | None = None) -> None:
    """复习后更新间隔：答对延长，答错缩短。仅在事件非重放时被调用（幂等由调用方保证）。

    复习提交链路（error_api.record_error_review）只接受真实正确作答，
    因此常规调用 correct=True；保留参数以支持后续引入"复习失败"事件。
    """
    now = now or datetime.now(timezone.utc)
    if getattr(item, "is_mastered", False):
        # 已毕业：退出复习队列
        item.next_review_at = None
        item.scheduler_version = SCHEDULER_VERSION
        return
    interval = compute_next_interval(
        current_interval_days=item.review_interval_days or 0, correct=correct,
    )
    item.review_interval_days = interval
    item.review_streak = (item.review_streak or 0) + 1 if correct else 0
    item.next_review_at = now + timedelta(days=interval)
    item.scheduler_version = SCHEDULER_VERSION


def _state_stage(state: str | None) -> int:
    return _STATE_STAGE.get(state or "new", 0)


async def get_due_reviews(
    db: AsyncSession, *, user_id: str, now: datetime | None = None,
    limit: int = 20, include_upcoming: bool = False,
) -> list[ErrorItem]:
    """返回该用户到期未毕业的错题，活跃错题（新错/理解中）优先于巩固中。

    include_upcoming=True 时同时返回尚未到期但已有排期的错题（供"未来复习计划"展示）。
    """
    now = now or datetime.now(timezone.utc)
    stage = case(
        *[(ErrorItem.review_state == state, value) for state, value in _STATE_STAGE.items()],
        else_=2,
    )
    conditions = [
        ErrorItem.user_id == user_id,
        ErrorItem.is_mastered.is_(False),
        ErrorItem.next_review_at.is_not(None),
    ]
    if not include_upcoming:
        conditions.append(ErrorItem.next_review_at <= now)
    stmt = (
        select(ErrorItem)
        .where(*conditions)
        .order_by(stage, ErrorItem.next_review_at, ErrorItem.id)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars())
